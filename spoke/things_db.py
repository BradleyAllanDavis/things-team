"""Read-only Things 3 database access for spokes — stdlib sqlite3 against a
things-mirror snapshot (never the live TCC-protected DB, never writes).

Field semantics reverse-engineered/verified per THINGS-INTERNALS.md:
- TMTask.status: 0 open, 2 canceled, 3 completed
- TMTask.type:   0 to-do, 1 project, 2 heading
- TMTask.start:  0 Inbox, 1 Anytime/Today, 2 Someday
- startDate/deadline: packed integer YYYYYYYYYYYMMMMDDDDD0000000 (binary)
- creationDate/userModificationDate: plain Unix epoch seconds (UTC)
- repeating: rt1_recurrenceRule (template) / rt1_repeatingTemplate (instance)

Python 3.9-compatible, stdlib only.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import time


def _log(msg: str) -> None:
    print(f"[things-team-reader] {msg}", file=sys.stderr, flush=True)


def _thingsdate(column: str) -> str:
    """SQL expression unpacking Things' packed date int to ISO — same
    expression things.py documents (and things-queue already uses)."""
    return (
        f"CASE WHEN {column} THEN printf('%04d-%02d-%02d', "
        f"({column} & 134152192) >> 16, ({column} & 61440) >> 12, "
        f"({column} & 3968) >> 7) ELSE NULL END"
    )


_STATUS_NAMES = {0: "open", 2: "canceled", 3: "completed"}


class MirrorReader:
    """ThingsReader over a things-mirror sqlite snapshot.

    kick_agent: launchd label of the local things-mirror agent to
    kickstart for a fresh snapshot before time-sensitive reads (Jill's
    Air / mini). None on the hub, where the mirror arrives passively via
    Syncthing and freshness is whatever the mesh delivers.
    """

    def __init__(self, mirror_path: str, kick_agent=None,
                 kick_timeout: float = 5.0):
        self.mirror_path = os.path.expanduser(mirror_path)
        self.kick_agent = kick_agent
        self.kick_timeout = kick_timeout

    # -- plumbing ---------------------------------------------------------
    def _conn(self) -> sqlite3.Connection:
        if not os.path.isfile(self.mirror_path):
            raise RuntimeError(f"things mirror not found at {self.mirror_path}")
        conn = sqlite3.connect(f"file:{self.mirror_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def refresh(self) -> None:
        if not self.kick_agent:
            return
        before = (os.path.getmtime(self.mirror_path)
                  if os.path.exists(self.mirror_path) else 0.0)
        try:
            subprocess.run(
                ["/bin/launchctl", "kickstart", "-k",
                 f"gui/{os.getuid()}/{self.kick_agent}"],
                capture_output=True, timeout=5)
        except Exception as exc:
            _log(f"mirror kickstart failed: {exc}")
            return
        deadline = time.time() + self.kick_timeout
        while time.time() < deadline:
            if (os.path.exists(self.mirror_path)
                    and os.path.getmtime(self.mirror_path) > before):
                return
            time.sleep(0.2)

    # -- ThingsReader interface ------------------------------------------
    def outbound_candidates(self, trigger_titles) -> list:
        """Open, untrashed TO-DOS carrying one of the trigger tags, matched
        on EXACT tag title (case-insensitive) — substring matching swept
        pre-existing tags like `Jillian 👩🏻‍🦰` and is banned (2026-07-11)."""
        if not trigger_titles:
            return []
        placeholders = ",".join("?" for _ in trigger_titles)
        sql = f"""
            SELECT DISTINCT t.uuid FROM TMTask t
            JOIN TMTaskTag tt ON tt.tasks = t.uuid
            JOIN TMTag tag ON tag.uuid = tt.tags
            WHERE lower(tag.title) IN ({placeholders})
              AND t.trashed = 0 AND t.status = 0 AND t.type = 0
        """
        conn = self._conn()
        try:
            uuids = [r["uuid"] for r in conn.execute(
                sql, [t.lower() for t in trigger_titles])]
            return [self._snapshot(conn, u) for u in uuids]
        finally:
            conn.close()

    def _snapshot(self, conn: sqlite3.Connection, uuid: str) -> dict:
        row = conn.execute(
            f"""SELECT uuid, title, notes, status, type, trashed, start,
                   {_thingsdate('startDate')} AS start_date,
                   {_thingsdate('deadline')} AS deadline_date,
                   rt1_recurrenceRule, rt1_repeatingTemplate
                FROM TMTask WHERE uuid = ?""", (uuid,)).fetchone()
        checklist = [r["title"] for r in conn.execute(
            'SELECT title FROM TMChecklistItem WHERE task = ?'
            ' ORDER BY "index"', (uuid,))]
        tags = [r["title"] for r in conn.execute(
            "SELECT tag.title FROM TMTaskTag tt JOIN TMTag tag ON tag.uuid = tt.tags"
            " WHERE tt.tasks = ?", (uuid,))]
        # when: only EXPLICIT scheduling crosses the wire — a scheduled date,
        # or someday. Anytime (the default resting state of most project
        # todos) maps to None → recipient's real Inbox (D3).
        when = row["start_date"]
        if when is None and row["start"] == 2:
            when = "someday"
        return {
            "uuid": row["uuid"],
            "title": row["title"] or "",
            "notes": row["notes"] or "",
            "checklist": checklist,
            "tags": tags,
            "when": when,
            "deadline": row["deadline_date"],
            "type": row["type"],
            "is_repeating": (row["rt1_recurrenceRule"] is not None
                             or row["rt1_repeatingTemplate"] is not None),
        }

    def status(self, uuid: str):
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT status, trashed FROM TMTask WHERE uuid = ?",
                (uuid,)).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        return {"status": _STATUS_NAMES.get(row["status"], "open"),
                "trashed": bool(row["trashed"])}

    def tags_of(self, uuid: str):
        conn = self._conn()
        try:
            if conn.execute("SELECT 1 FROM TMTask WHERE uuid = ?",
                            (uuid,)).fetchone() is None:
                return None
            return [r["title"] for r in conn.execute(
                "SELECT tag.title FROM TMTaskTag tt"
                " JOIN TMTag tag ON tag.uuid = tt.tags WHERE tt.tasks = ?",
                (uuid,))]
        finally:
            conn.close()

    def correlate(self, title: str, created_after: float, provenance_tag: str,
                  exclude_uuids) -> str:
        """Read-after-write uuid discovery for a just-created todo: exact
        title + created in the window + carrying the provenance tag (only
        sync-created todos ever carry it) + not already known."""
        conn = self._conn()
        try:
            rows = conn.execute(
                """SELECT t.uuid FROM TMTask t
                   JOIN TMTaskTag tt ON tt.tasks = t.uuid
                   JOIN TMTag tag ON tag.uuid = tt.tags
                   WHERE t.title = ? AND t.creationDate >= ?
                     AND lower(tag.title) = ? AND t.trashed = 0
                   ORDER BY t.creationDate ASC""",
                (title, created_after, provenance_tag.lower())).fetchall()
        finally:
            conn.close()
        for r in rows:
            if r["uuid"] not in exclude_uuids:
                return r["uuid"]
        return None
