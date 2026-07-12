"""tandem hub ledger — the single stateful coordinator.

SQLite (WAL), stdlib-only. Every row roots at a tenant; every query is
scoped through the authenticated Principal's tenant — cross-tenant
references are impossible to express through this API (no tenant
parameter is ever accepted from a client; it comes from auth).

Schema and invariants: DESIGN.md §4. State machines: PROTOCOL.md.

Key invariants, and where they live:

- No-loss: transfers and deliveries are durably committed (fsync via
  sqlite) before any caller is told to mutate Things. Deliveries persist
  until acked; leases expire and re-queue.
- No-dup: UNIQUE(tenant, from_member, src_uuid, rev) makes transfer
  pushes idempotent (replays return the existing row);
  UNIQUE(transfer, kind, to_member) makes delivery queuing idempotent.
- Completion round-trip: terminal state is set-once at the hub
  (completed beats canceled); the echo is just another idempotent
  delivery to the other party.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import threading
import time
import uuid as uuidlib
from dataclasses import dataclass

TERMINAL_STATES = ("completed", "canceled")
# terminal state -> echo delivery kind
_ECHO_KIND = {"completed": "complete", "canceled": "cancel"}

# Provenance tag emoji suffix per member handle (2026-07-11) -- matches the
# emoji already used for these people elsewhere in Bradley's Things/docs
# (docs/context.md uses "Bradley 👨" / "Jillian 👩"; the pre-existing Things
# tag is "Jillian 👩🏻‍🦰"). Unlisted handles get no emoji (plain "from-<handle>"
# still works, just not tagged with a face) -- add here when a new member's
# person-emoji is decided, no code change needed beyond this dict. Must be
# pre-created as a real tag in the RECIPIENT's Things (unknown tags are
# silently dropped by the URL scheme).
_PROVENANCE_EMOJI = {
    "bradley": "👨",
    "jill": "👩🏻‍🦰",
}


def provenance_tag(handle: str) -> str:
    emoji = _PROVENANCE_EMOJI.get(handle)
    return f"from-{handle} {emoji}" if emoji else f"from-{handle}"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL UNIQUE,
  created_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS members (
  id           TEXT PRIMARY KEY,
  tenant_id    TEXT NOT NULL REFERENCES tenants(id),
  handle       TEXT NOT NULL,
  display_name TEXT NOT NULL,
  can_send     INTEGER NOT NULL DEFAULT 1,
  can_receive  INTEGER NOT NULL DEFAULT 1,
  can_admin    INTEGER NOT NULL DEFAULT 0,
  created_at   REAL NOT NULL,
  UNIQUE(tenant_id, handle)
);

CREATE TABLE IF NOT EXISTS devices (
  id           TEXT PRIMARY KEY,
  member_id    TEXT NOT NULL REFERENCES members(id),
  name         TEXT NOT NULL,
  token_hash   TEXT UNIQUE,          -- sha256 hex; plaintext shown once at issue
  created_at   REAL NOT NULL,
  last_seen_at REAL,
  revoked_at   REAL
);

CREATE TABLE IF NOT EXISTS transfers (
  id           TEXT PRIMARY KEY,
  tenant_id    TEXT NOT NULL REFERENCES tenants(id),
  from_member  TEXT NOT NULL REFERENCES members(id),
  to_member    TEXT NOT NULL REFERENCES members(id),
  src_uuid     TEXT NOT NULL,        -- Things uuid, sender side (natural key)
  dst_uuid     TEXT,                 -- Things uuid, recipient side; set at create-ack
  rev          INTEGER NOT NULL DEFAULT 1,
  payload      TEXT NOT NULL,        -- JSON envelope (PROTOCOL.md)
  terminal     TEXT CHECK (terminal IN ('completed','canceled')),
  terminal_by  TEXT REFERENCES members(id),
  created_at   REAL NOT NULL,
  applied_at   REAL,
  resolved_at  REAL,
  UNIQUE(tenant_id, from_member, src_uuid, rev)
);

CREATE TABLE IF NOT EXISTS deliveries (
  id                TEXT PRIMARY KEY,
  transfer_id       TEXT NOT NULL REFERENCES transfers(id),
  kind              TEXT NOT NULL CHECK (kind IN ('create','complete','cancel')),
  to_member         TEXT NOT NULL REFERENCES members(id),
  state             TEXT NOT NULL CHECK (state IN ('queued','leased','done')),
  leased_by_device  TEXT,
  lease_expires_at  REAL,
  attempts          INTEGER NOT NULL DEFAULT 0,
  last_error        TEXT,
  created_at        REAL NOT NULL,
  done_at           REAL,
  UNIQUE(transfer_id, kind, to_member)
);

CREATE TABLE IF NOT EXISTS events (
  id          TEXT PRIMARY KEY,
  transfer_id TEXT,
  device_id   TEXT,
  kind        TEXT NOT NULL,
  detail      TEXT,
  created_at  REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_deliveries_member_state
  ON deliveries (to_member, state);
CREATE INDEX IF NOT EXISTS idx_transfers_open
  ON transfers (tenant_id, resolved_at);
"""


class LedgerError(Exception):
    status = 400


class AuthError(LedgerError):
    status = 401


class Forbidden(LedgerError):
    status = 403


class NotFound(LedgerError):
    status = 404


@dataclass(frozen=True)
class Principal:
    tenant_id: str
    member_id: str
    device_id: str
    handle: str
    can_send: bool
    can_receive: bool
    can_admin: bool


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_id() -> str:
    return str(uuidlib.uuid4())


class Ledger:
    """One connection, one lock — plenty at family scale, and it keeps
    every state transition trivially serializable."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.lock = threading.RLock()
        # Push primitive: a CV with its OWN lock (never the data RLock) and a
        # monotonic generation counter. Every delivery-CREATING commit bumps
        # the generation and notifies; a parked reader (HTTP long-poll or the
        # in-process gateway inbound loop) wakes the instant work is ready
        # instead of busy-polling. One global generation — a spurious wakeup
        # for the wrong member costs one cheap re-query at family scale, and
        # it keeps the data lock out of the CV predicate. See DESIGN §6b.
        self._new_delivery = threading.Condition()
        self._delivery_gen = 0
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        with self.lock, self.conn:
            self.conn.executescript(_SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # -- push primitive ----------------------------------------------------
    def wait_for_delivery(self, timeout: float) -> None:
        """Block until a new delivery is queued (generation advances) or the
        timeout elapses. Never touches the data lock — safe to call between
        lease_deliveries() re-checks. A non-positive timeout returns at once."""
        if timeout <= 0:
            return
        with self._new_delivery:
            gen = self._delivery_gen
            self._new_delivery.wait_for(
                lambda: self._delivery_gen != gen, timeout)

    def _signal_delivery(self) -> None:
        """Announce that a leasable delivery was just committed. MUST be
        called AFTER the data transaction commits (not inside it): a waiter
        woken while the write is still uncommitted could re-query, miss the
        row, and re-park — reintroducing a latency floor."""
        with self._new_delivery:
            self._delivery_gen += 1
            self._new_delivery.notify_all()

    # -- events ----------------------------------------------------------
    def _event(self, kind: str, transfer_id=None, device_id=None, detail=None) -> None:
        self.conn.execute(
            "INSERT INTO events (id, transfer_id, device_id, kind, detail, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (_new_id(), transfer_id, device_id, kind,
             json.dumps(detail) if detail is not None else None, time.time()),
        )

    # -- admin -------------------------------------------------------------
    def create_tenant(self, name: str) -> dict:
        with self.lock, self.conn:
            tid = _new_id()
            try:
                self.conn.execute(
                    "INSERT INTO tenants (id, name, created_at) VALUES (?,?,?)",
                    (tid, name, time.time()),
                )
            except sqlite3.IntegrityError:
                raise LedgerError(f"tenant {name!r} already exists")
            return {"id": tid, "name": name}

    def create_member(self, tenant_id: str, handle: str, display_name: str,
                      can_send=True, can_receive=True, can_admin=False) -> dict:
        handle = handle.strip().lower()
        if not handle:
            raise LedgerError("handle is required")
        with self.lock, self.conn:
            if not self.conn.execute("SELECT 1 FROM tenants WHERE id=?", (tenant_id,)).fetchone():
                raise NotFound(f"no tenant {tenant_id}")
            mid = _new_id()
            try:
                self.conn.execute(
                    "INSERT INTO members (id, tenant_id, handle, display_name,"
                    " can_send, can_receive, can_admin, created_at)"
                    " VALUES (?,?,?,?,?,?,?,?)",
                    (mid, tenant_id, handle, display_name,
                     int(can_send), int(can_receive), int(can_admin), time.time()),
                )
            except sqlite3.IntegrityError:
                raise LedgerError(f"member {handle!r} already exists in tenant")
            return {"id": mid, "tenant_id": tenant_id, "handle": handle,
                    "display_name": display_name}

    def create_device(self, member_id: str, name: str) -> dict:
        """Returns the plaintext token EXACTLY ONCE — only the sha256 is stored."""
        with self.lock, self.conn:
            if not self.conn.execute("SELECT 1 FROM members WHERE id=?", (member_id,)).fetchone():
                raise NotFound(f"no member {member_id}")
            did = _new_id()
            token = secrets.token_urlsafe(32)
            self.conn.execute(
                "INSERT INTO devices (id, member_id, name, token_hash, created_at)"
                " VALUES (?,?,?,?,?)",
                (did, member_id, name, _hash_token(token), time.time()),
            )
            return {"id": did, "member_id": member_id, "name": name, "token": token}

    def revoke_device(self, device_id: str) -> None:
        with self.lock, self.conn:
            cur = self.conn.execute(
                "UPDATE devices SET revoked_at=?, token_hash=NULL WHERE id=? AND revoked_at IS NULL",
                (time.time(), device_id),
            )
            if cur.rowcount == 0:
                raise NotFound(f"no active device {device_id}")

    def ensure_gateway_device(self, member_id: str, name: str = "gateway") -> str:
        """Idempotently ensure a tokenless internal device row for the
        in-process gateway worker (it authenticates by construction, not by
        token — see DirectHubClient)."""
        with self.lock, self.conn:
            row = self.conn.execute(
                "SELECT id FROM devices WHERE member_id=? AND name=? AND revoked_at IS NULL",
                (member_id, name),
            ).fetchone()
            if row:
                return row["id"]
            did = _new_id()
            self.conn.execute(
                "INSERT INTO devices (id, member_id, name, token_hash, created_at)"
                " VALUES (?,?,?,NULL,?)",
                (did, member_id, name, time.time()),
            )
            return did

    # -- auth ----------------------------------------------------------------
    def authenticate(self, token: str) -> Principal:
        if not token:
            raise AuthError("missing token")
        with self.lock:
            row = self.conn.execute(
                "SELECT d.id AS device_id, m.id AS member_id, m.tenant_id, m.handle,"
                " m.can_send, m.can_receive, m.can_admin"
                " FROM devices d JOIN members m ON m.id = d.member_id"
                " WHERE d.token_hash=? AND d.revoked_at IS NULL",
                (_hash_token(token),),
            ).fetchone()
            if row is None:
                raise AuthError("invalid or revoked token")
            with self.conn:
                self.conn.execute("UPDATE devices SET last_seen_at=? WHERE id=?",
                                  (time.time(), row["device_id"]))
            return Principal(
                tenant_id=row["tenant_id"], member_id=row["member_id"],
                device_id=row["device_id"], handle=row["handle"],
                can_send=bool(row["can_send"]), can_receive=bool(row["can_receive"]),
                can_admin=bool(row["can_admin"]),
            )

    def principal_for_member(self, member_id: str, device_id: str) -> Principal:
        """Construct a Principal without a token — used ONLY by the
        in-process gateway worker (same trust domain as the ledger itself)."""
        with self.lock:
            row = self.conn.execute(
                "SELECT id, tenant_id, handle, can_send, can_receive, can_admin"
                " FROM members WHERE id=?", (member_id,)).fetchone()
            if row is None:
                raise NotFound(f"no member {member_id}")
            return Principal(
                tenant_id=row["tenant_id"], member_id=row["id"], device_id=device_id,
                handle=row["handle"], can_send=bool(row["can_send"]),
                can_receive=bool(row["can_receive"]), can_admin=bool(row["can_admin"]),
            )

    def member_by_handle(self, tenant_id: str, handle: str):
        with self.lock:
            return self.conn.execute(
                "SELECT * FROM members WHERE tenant_id=? AND handle=?",
                (tenant_id, handle.strip().lower()),
            ).fetchone()

    # -- transfers -------------------------------------------------------------
    def push_transfer(self, p: Principal, to_handle: str, src_uuid: str,
                      payload: dict, rev: int = 1) -> dict:
        if not p.can_send:
            raise Forbidden("member lacks can_send")
        if not src_uuid or not isinstance(payload, dict):
            raise LedgerError("src_uuid and payload are required")
        if not payload.get("title"):
            raise LedgerError("payload.title is required")
        with self.lock, self.conn:
            to = self.member_by_handle(p.tenant_id, to_handle)
            if to is None:
                raise NotFound(f"no member {to_handle!r} in tenant")
            if to["id"] == p.member_id:
                raise LedgerError("cannot delegate to yourself")
            if not to["can_receive"]:
                raise Forbidden(f"member {to_handle!r} lacks can_receive")

            existing = self.conn.execute(
                "SELECT * FROM transfers WHERE tenant_id=? AND from_member=?"
                " AND src_uuid=? AND rev=?",
                (p.tenant_id, p.member_id, src_uuid, rev),
            ).fetchone()
            if existing:
                rec = self._transfer_dict(existing)
                rec["deduped"] = True
                return rec

            tid = _new_id()
            now = time.time()
            self.conn.execute(
                "INSERT INTO transfers (id, tenant_id, from_member, to_member,"
                " src_uuid, rev, payload, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (tid, p.tenant_id, p.member_id, to["id"], src_uuid, rev,
                 json.dumps(payload), now),
            )
            self.conn.execute(
                "INSERT OR IGNORE INTO deliveries (id, transfer_id, kind, to_member,"
                " state, created_at) VALUES (?,?,?,?,?,?)",
                (_new_id(), tid, "create", to["id"], "queued", now),
            )
            self._event("transfer-pushed", tid, p.device_id,
                        {"to": to_handle, "src_uuid": src_uuid, "rev": rev})
            rec = self._transfer_dict(self.conn.execute(
                "SELECT * FROM transfers WHERE id=?", (tid,)).fetchone())
            rec["deduped"] = False
        # committed above — wake any spoke long-polling for this recipient
        self._signal_delivery()
        return rec

    def _transfer_dict(self, row) -> dict:
        return {
            "id": row["id"], "src_uuid": row["src_uuid"], "dst_uuid": row["dst_uuid"],
            "rev": row["rev"], "terminal": row["terminal"],
            "created_at": row["created_at"], "applied_at": row["applied_at"],
            "resolved_at": row["resolved_at"],
        }

    def get_transfer(self, transfer_id: str):
        with self.lock:
            return self.conn.execute(
                "SELECT * FROM transfers WHERE id=?", (transfer_id,)).fetchone()

    # -- deliveries ----------------------------------------------------------
    def lease_deliveries(self, p: Principal, limit: int, lease_seconds: float) -> list:
        """Lease queued (or lease-expired) deliveries for this member.

        Ordering guard: a terminal-kind delivery for a transfer is never
        handed out while that transfer's create delivery to the same member
        isn't done, and never to the recipient before dst_uuid exists —
        the recipient can't complete a todo it hasn't created yet.
        """
        if not p.can_receive:
            raise Forbidden("member lacks can_receive")
        now = time.time()
        with self.lock, self.conn:
            rows = self.conn.execute(
                "SELECT d.*, t.payload, t.src_uuid, t.dst_uuid, t.terminal,"
                "       t.from_member, t.to_member, t.id AS tid,"
                "       fm.handle AS from_handle"
                " FROM deliveries d"
                " JOIN transfers t ON t.id = d.transfer_id"
                " JOIN members fm ON fm.id = t.from_member"
                " WHERE d.to_member=? AND d.state != 'done'"
                " ORDER BY d.created_at",
                (p.member_id,),
            ).fetchall()
            leased = []
            for d in rows:
                if len(leased) >= limit:
                    break
                if d["state"] == "leased" and (d["lease_expires_at"] or 0) >= now:
                    continue  # live lease held elsewhere
                # uuid this delivery acts on: the echo recipient acts on their
                # own copy — src_uuid if they were the sender, dst_uuid if the
                # recipient (and never before that copy exists).
                if d["kind"] in ("complete", "cancel"):
                    if d["to_member"] == d["from_member"]:
                        uuid_to_act = d["src_uuid"]
                    else:
                        if not d["dst_uuid"]:
                            continue  # recipient hasn't created it yet
                        uuid_to_act = d["dst_uuid"]
                else:
                    uuid_to_act = None
                self.conn.execute(
                    "UPDATE deliveries SET state='leased', leased_by_device=?,"
                    " lease_expires_at=?, attempts=attempts+1 WHERE id=?",
                    (p.device_id, now + lease_seconds, d["id"]),
                )
                entry = {
                    "id": d["id"], "transfer_id": d["tid"], "kind": d["kind"],
                    "attempts": d["attempts"] + 1,
                }
                if d["kind"] == "create":
                    entry["payload"] = json.loads(d["payload"])
                    entry["from"] = d["from_handle"]
                    entry["provenance_tag"] = provenance_tag(d["from_handle"])
                else:
                    entry["uuid"] = uuid_to_act
                leased.append(entry)
            return leased

    def ack_delivery(self, p: Principal, delivery_id: str, dst_uuid=None) -> dict:
        queued_echo = False
        with self.lock, self.conn:
            d = self.conn.execute(
                "SELECT d.*, t.terminal, t.from_member, t.to_member, t.applied_at,"
                " t.resolved_at FROM deliveries d JOIN transfers t ON t.id=d.transfer_id"
                " WHERE d.id=? AND d.to_member=?",
                (delivery_id, p.member_id),
            ).fetchone()
            if d is None:
                raise NotFound("no such delivery for this member")
            if d["state"] == "done":
                return {"ok": True, "already_done": True}
            now = time.time()
            if d["kind"] == "create":
                if not dst_uuid:
                    raise LedgerError("create ack requires dst_uuid")
                self.conn.execute(
                    "UPDATE transfers SET dst_uuid=?, applied_at=COALESCE(applied_at, ?)"
                    " WHERE id=?", (dst_uuid, now, d["transfer_id"]))
                self.conn.execute(
                    "UPDATE deliveries SET state='done', done_at=? WHERE id=?",
                    (now, delivery_id))
                self._event("create-applied", d["transfer_id"], p.device_id,
                            {"dst_uuid": dst_uuid})
                # Sender revoked while the create was in flight: queue the
                # terminal echo to the recipient now that dst_uuid exists.
                if d["terminal"]:
                    self.conn.execute(
                        "INSERT OR IGNORE INTO deliveries (id, transfer_id, kind,"
                        " to_member, state, created_at) VALUES (?,?,?,?,?,?)",
                        (_new_id(), d["transfer_id"], _ECHO_KIND[d["terminal"]],
                         d["to_member"], "queued", now))
                    queued_echo = True
            else:
                self.conn.execute(
                    "UPDATE deliveries SET state='done', done_at=? WHERE id=?",
                    (now, delivery_id))
                self.conn.execute(
                    "UPDATE transfers SET resolved_at=COALESCE(resolved_at, ?) WHERE id=?",
                    (now, d["transfer_id"]))
                self._event("terminal-echoed", d["transfer_id"], p.device_id,
                            {"kind": d["kind"]})
        if queued_echo:  # committed above — wake the recipient's poll
            self._signal_delivery()
        return {"ok": True}

    def nack_delivery(self, p: Principal, delivery_id: str, error: str) -> dict:
        with self.lock, self.conn:
            d = self.conn.execute(
                "SELECT * FROM deliveries WHERE id=? AND to_member=?",
                (delivery_id, p.member_id)).fetchone()
            if d is None:
                raise NotFound("no such delivery for this member")
            if d["state"] == "done":
                return {"ok": True, "already_done": True}
            self.conn.execute(
                "UPDATE deliveries SET state='queued', leased_by_device=NULL,"
                " lease_expires_at=NULL, last_error=? WHERE id=?",
                (str(error)[:500], delivery_id))
            self._event("delivery-nacked", d["transfer_id"], p.device_id,
                        {"delivery": delivery_id, "error": str(error)[:500]})
            return {"ok": True}

    # -- watch + observations ----------------------------------------------
    def watchlist(self, p: Principal) -> list:
        """Open transfers this member observes: their own copy's uuid + role.
        Also carries transfer state so a sender spoke can retag after apply."""
        out = []
        with self.lock:
            rows = self.conn.execute(
                "SELECT * FROM transfers WHERE tenant_id=? AND resolved_at IS NULL"
                " AND terminal IS NULL AND (from_member=? OR to_member=?)",
                (p.tenant_id, p.member_id, p.member_id),
            ).fetchall()
        for t in rows:
            state = "applied" if t["applied_at"] else "created"
            if t["from_member"] == p.member_id:
                out.append({"transfer_id": t["id"], "uuid": t["src_uuid"],
                            "role": "sender", "state": state})
            elif t["dst_uuid"]:
                out.append({"transfer_id": t["id"], "uuid": t["dst_uuid"],
                            "role": "recipient", "state": state})
        return out

    def observe(self, p: Principal, transfer_id: str, state: str) -> dict:
        """Report a terminal state seen on a watched copy. Set-once, with the
        one sanctioned upgrade: completed beats canceled (work done wins) as
        long as the canceled echo hasn't already been delivered."""
        if state not in TERMINAL_STATES:
            raise LedgerError(f"state must be one of {TERMINAL_STATES}")
        queued_echo = False
        with self.lock, self.conn:
            t = self.conn.execute(
                "SELECT * FROM transfers WHERE id=? AND tenant_id=?"
                " AND (from_member=? OR to_member=?)",
                (transfer_id, p.tenant_id, p.member_id, p.member_id),
            ).fetchone()
            if t is None:
                raise NotFound("no such transfer for this member")
            now = time.time()
            if t["terminal"]:
                if t["terminal"] == state:
                    result = {"ok": True, "terminal": state, "already_set": True}
                elif t["terminal"] == "canceled" and state == "completed":
                    echo_done = self.conn.execute(
                        "SELECT 1 FROM deliveries WHERE transfer_id=? AND kind='cancel'"
                        " AND state='done'", (transfer_id,)).fetchone()
                    if echo_done:
                        self._event("terminal-upgrade-refused", transfer_id,
                                    p.device_id, {"kept": "canceled"})
                        result = {"ok": True, "terminal": "canceled",
                                  "already_set": True}
                    else:
                        # upgrade: completed beats canceled
                        self.conn.execute(
                            "UPDATE transfers SET terminal='completed', terminal_by=?"
                            " WHERE id=?", (p.member_id, transfer_id))
                        self.conn.execute(
                            "DELETE FROM deliveries WHERE transfer_id=? AND kind='cancel'"
                            " AND state != 'done'", (transfer_id,))
                        queued_echo = self._queue_echo(t, "completed", now)
                        self._event("terminal-upgraded", transfer_id, p.device_id,
                                    {"from": "canceled", "to": "completed"})
                        result = {"ok": True, "terminal": "completed"}
                else:
                    # completed already set; canceled arrives → completed wins
                    result = {"ok": True, "terminal": "completed", "already_set": True}
            else:
                self.conn.execute(
                    "UPDATE transfers SET terminal=?, terminal_by=? WHERE id=?",
                    (state, p.member_id, transfer_id))
                self._event("terminal-set", transfer_id, p.device_id,
                            {"state": state, "by": p.handle})
                queued_echo = self._queue_echo(t, state, now)
                result = {"ok": True, "terminal": state}
        if queued_echo:  # committed above — wake the echo recipient's poll
            self._signal_delivery()
        return result

    def _queue_echo(self, t_row, state: str, now: float) -> bool:
        """Returns True iff a new leasable ('queued') echo delivery was
        inserted (the caller signals the CV after commit)."""
        """Queue the terminal echo to the party that did NOT report it.
        Special case: sender revoked before the recipient ever applied the
        create — skip the create outright (never materialize a dead todo)
        and resolve; if the create is mid-flight (leased), ack_delivery
        queues the echo once dst_uuid exists."""
        t = self.conn.execute("SELECT * FROM transfers WHERE id=?",
                              (t_row["id"],)).fetchone()
        terminal_by = t["terminal_by"]
        other = t["to_member"] if terminal_by == t["from_member"] else t["from_member"]
        if other == t["to_member"] and not t["dst_uuid"]:
            create = self.conn.execute(
                "SELECT * FROM deliveries WHERE transfer_id=? AND kind='create'",
                (t["id"],)).fetchone()
            if create and create["state"] == "queued":
                self.conn.execute(
                    "UPDATE deliveries SET state='done', done_at=?, last_error="
                    "'skipped: sender resolved before apply' WHERE id=?",
                    (now, create["id"]))
                self.conn.execute(
                    "UPDATE transfers SET resolved_at=COALESCE(resolved_at, ?)"
                    " WHERE id=?", (now, t["id"]))
                self._event("create-skipped-terminal", t["id"], None,
                            {"terminal": state})
                return False  # create suppressed, nothing leasable queued
            if create and create["state"] == "leased":
                return False  # ack_delivery will queue the echo when dst_uuid lands
        self.conn.execute(
            "INSERT OR IGNORE INTO deliveries (id, transfer_id, kind, to_member,"
            " state, created_at) VALUES (?,?,?,?,?,?)",
            (_new_id(), t["id"], _ECHO_KIND[state], other, "queued", now))
        return True

    # -- health -------------------------------------------------------------
    def health(self) -> dict:
        with self.lock:
            pending = self.conn.execute(
                "SELECT COUNT(*) FROM deliveries WHERE state != 'done'").fetchone()[0]
            open_transfers = self.conn.execute(
                "SELECT COUNT(*) FROM transfers WHERE resolved_at IS NULL").fetchone()[0]
            return {"ok": True, "pending_deliveries": pending,
                    "open_transfers": open_transfers}
