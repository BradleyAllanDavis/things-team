"""things-team hub entrypoint — HTTP API + declarative bootstrap + the
in-process gateway worker.

Configuration is environment-driven (set by the nix module):

  THINGS_TEAM_PORT / THINGS_TEAM_BIND      HTTP API (default 8712 / 0.0.0.0)
  STATE_DIRECTORY                          ledger + gateway spoke state
  THINGS_TEAM_BOOTSTRAP                    JSON — declarative tenant/members/
                                           devices, ensured idempotently at
                                           startup (see below)
  THINGS_TEAM_GATEWAY_MEMBER               handle whose side runs in-process
                                           via the things-gateway (bradley)
  THINGS_TEAM_TRIGGER_TAGS                 JSON {recipient_handle: [exact tag
                                           titles]} for the gateway member's
                                           outbound scan
  THINGS_MIRROR_DB                         synced Things DB mirror path
  THINGS_QUEUE_URL                         things-queue base URL
  CREDENTIALS_DIRECTORY/queue-token        things-queue bearer token
  CREDENTIALS_DIRECTORY/<name>             spoke device tokens (bootstrap
                                           "token_credential" entries)
  THINGS_TEAM_TICK_SECONDS                 gateway tick interval (default 60)

Bootstrap JSON shape (1Password stays canonical for tokens; the hub only
ever stores the sha256 of what the deploy materialized):

  {"tenant": "davis",
   "members": [{"handle": "bradley", "display_name": "Bradley", "admin": true},
               {"handle": "jill",    "display_name": "Jill"}],
   "devices": [{"member": "jill", "name": "jill-air",
                "token_credential": "jill-air-token"}]}
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
import uuid as uuidlib

from .api import make_server
from .direct import DirectHubClient
from .ledger import Ledger


def _log(msg: str) -> None:
    print(f"[things-team-hub] {msg}", file=sys.stderr, flush=True)


def _credential(name: str):
    creds_dir = os.environ.get("CREDENTIALS_DIRECTORY")
    if not creds_dir:
        return None
    path = os.path.join(creds_dir, name)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return f.read().strip()


def bootstrap(ledger: Ledger, spec: dict) -> None:
    """Idempotently ensure tenant / members / provisioned spoke devices.
    Token rotation = new file contents + service restart; the row's hash
    is updated in place."""
    tenant_name = spec["tenant"]
    with ledger.lock, ledger.conn:
        row = ledger.conn.execute("SELECT id FROM tenants WHERE name=?",
                                  (tenant_name,)).fetchone()
    tenant_id = row["id"] if row else ledger.create_tenant(tenant_name)["id"]

    for m in spec.get("members", []):
        if ledger.member_by_handle(tenant_id, m["handle"]) is None:
            ledger.create_member(
                tenant_id, m["handle"], m.get("display_name", m["handle"]),
                can_send=m.get("can_send", True),
                can_receive=m.get("can_receive", True),
                can_admin=m.get("admin", False))
            _log(f"bootstrap: created member {m['handle']!r}")

    for d in spec.get("devices", []):
        member = ledger.member_by_handle(tenant_id, d["member"])
        if member is None:
            _log(f"bootstrap: no member {d['member']!r} for device {d['name']!r}")
            continue
        token = _credential(d["token_credential"])
        if not token:
            _log(f"bootstrap: credential {d['token_credential']!r} missing — "
                 f"device {d['name']!r} not provisioned")
            continue
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with ledger.lock, ledger.conn:
            row = ledger.conn.execute(
                "SELECT id, token_hash FROM devices WHERE member_id=? AND name=?"
                " AND revoked_at IS NULL", (member["id"], d["name"])).fetchone()
            if row is None:
                ledger.conn.execute(
                    "INSERT INTO devices (id, member_id, name, token_hash,"
                    " created_at) VALUES (?,?,?,?,?)",
                    (str(uuidlib.uuid4()), member["id"], d["name"],
                     token_hash, time.time()))
                _log(f"bootstrap: provisioned device {d['name']!r} for {d['member']!r}")
            elif row["token_hash"] != token_hash:
                ledger.conn.execute(
                    "UPDATE devices SET token_hash=? WHERE id=?",
                    (token_hash, row["id"]))
                _log(f"bootstrap: rotated token for device {d['name']!r}")


def run_gateway_worker(ledger: Ledger, tenant_name: str) -> None:
    """The in-process spoke for the gateway member (Bradley): reader = the
    Syncthing-synced mirror on this host, writer = the things-queue, hub =
    direct ledger calls. Same SpokeCore Jill's Air runs."""
    from spoke.core import SpokeCore, SpokeState
    from spoke.things_db import MirrorReader
    from spoke.writer_queue import QueueWriter

    handle = os.environ["THINGS_TEAM_GATEWAY_MEMBER"]
    trigger_tags = json.loads(os.environ.get("THINGS_TEAM_TRIGGER_TAGS", "{}"))
    mirror_path = os.environ.get("THINGS_MIRROR_DB",
                                 "/var/lib/things-mirror/main.sqlite")
    queue_url = os.environ.get("THINGS_QUEUE_URL", "http://127.0.0.1:8090")
    tick_seconds = float(os.environ.get("THINGS_TEAM_TICK_SECONDS", "60"))
    state_dir = os.environ.get("STATE_DIRECTORY", "/var/lib/things-team")

    def queue_token():
        token = _credential("queue-token")
        if not token:
            raise RuntimeError("queue-token credential missing")
        return token

    # wait for bootstrap-provisioned member to exist (it should already)
    member = None
    while member is None:
        with ledger.lock:
            row = ledger.conn.execute(
                "SELECT m.id FROM members m JOIN tenants t ON t.id=m.tenant_id"
                " WHERE t.name=? AND m.handle=?", (tenant_name, handle)).fetchone()
        if row:
            member = row["id"]
            break
        _log(f"gateway: member {handle!r} not provisioned yet; retrying in 30s")
        time.sleep(30)

    device_id = ledger.ensure_gateway_device(member)
    principal = ledger.principal_for_member(member, device_id)
    core = SpokeCore(
        reader=MirrorReader(mirror_path),  # passive freshness (Syncthing)
        writer=QueueWriter(queue_url, queue_token),
        hub=DirectHubClient(ledger, principal),
        state=SpokeState(os.path.join(state_dir, "gateway-spoke.sqlite")),
        trigger_tags=trigger_tags,
    )
    _log(f"gateway worker up: member={handle}, triggers={trigger_tags}, "
         f"mirror={mirror_path}, queue={queue_url}")
    while True:
        try:
            core.tick()
        except Exception as exc:  # noqa: BLE001 — a bad tick never kills the hub
            _log(f"gateway tick error: {exc!r}")
        time.sleep(tick_seconds)


def main() -> None:
    state_dir = os.environ.get("STATE_DIRECTORY") or os.environ.get(
        "THINGS_TEAM_STATE_DIR", "/var/lib/things-team")
    os.makedirs(state_dir, exist_ok=True)
    ledger = Ledger(os.path.join(state_dir, "ledger.sqlite"))

    spec = None
    raw = os.environ.get("THINGS_TEAM_BOOTSTRAP", "")
    if raw:
        spec = json.loads(raw)
        bootstrap(ledger, spec)

    if os.environ.get("THINGS_TEAM_GATEWAY_MEMBER"):
        if not spec:
            _log("THINGS_TEAM_GATEWAY_MEMBER set but no THINGS_TEAM_BOOTSTRAP — "
                 "cannot resolve tenant; gateway worker disabled")
        else:
            threading.Thread(
                target=run_gateway_worker, args=(ledger, spec["tenant"]),
                daemon=True, name="gateway-worker").start()

    bind = os.environ.get("THINGS_TEAM_BIND", "0.0.0.0")
    port = int(os.environ.get("THINGS_TEAM_PORT", "8712"))
    server = make_server(ledger, bind, port)
    _log(f"listening on {bind}:{port}, ledger={ledger.db_path}")
    server.serve_forever()


if __name__ == "__main__":
    main()
