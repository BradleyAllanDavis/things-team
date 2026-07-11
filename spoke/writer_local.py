"""ThingsWriter backed by local `things:///json` opens — the writer for a
real Mac spoke (Jill's MacBook Air). One open per write, verified against
the local mirror by the caller (creates: SpokeCore.correlate; updates:
verified here with a bounded poll).

Focus discipline (ported from the things-gateway applier, where it's
load-bearing): Things.app can enter a state where it self-activates on ANY
write — `open -g` does not prevent it, and macOS offers no structural
third-party veto. The only viable technique is reactive: capture the
frontmost app before the write, watch across a settle window, and knock
back any steal observed (verify-and-retry, since macOS 26 can silently
swallow an activate() call). Never fight the user: if Things was already
frontmost with no recent steal from us, don't restore.

Python 3.9-compatible, stdlib only — runs on Apple's /usr/bin/python3.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from urllib.parse import quote

SETTLE_SECONDS = 3.0
FRONT_SAMPLE_INTERVAL = 0.2
STEAL_RECENCY_SECONDS = 60.0
THINGS_FRONT_NAME = "Things"  # lsappinfo LSDisplayName (process is Things3)
VERIFY_TIMEOUT = 30.0
VERIFY_INTERVAL = 1.0


def _log(msg: str) -> None:
    print(f"[things-team-lwriter] {msg}", file=sys.stderr, flush=True)


def _frontmost_name():
    try:
        asn = subprocess.run(["lsappinfo", "front"], capture_output=True,
                             text=True, timeout=5).stdout.strip()
        if not asn:
            return None
        out = subprocess.run(["lsappinfo", "info", "-only", "name", asn],
                             capture_output=True, text=True, timeout=5).stdout.strip()
        parts = out.split('"')
        return parts[3] if len(parts) >= 4 else None
    except Exception:
        return None


def _activate(app_name: str) -> None:
    try:
        subprocess.run(
            ["osascript", "-e", f'tell application "{app_name}" to activate'],
            capture_output=True, timeout=5)
    except Exception as exc:
        _log(f"activate {app_name} failed: {exc}")


class LocalWriter:
    def __init__(self, things_auth_token_provider, reader):
        self.token_provider = things_auth_token_provider  # callable -> str
        self.reader = reader  # MirrorReader on the same Mac (verification)
        self._last_good_front = None
        self._last_steal_ts = 0.0

    # -- focus watchdog -----------------------------------------------------
    def _capture(self):
        front = _frontmost_name()
        if front and front != THINGS_FRONT_NAME:
            self._last_good_front = front
            return True, front
        if (front == THINGS_FRONT_NAME and self._last_good_front
                and time.time() - self._last_steal_ts < STEAL_RECENCY_SECONDS):
            return True, self._last_good_front  # residue from our own steal
        return False, None  # user is genuinely in Things — don't fight them

    def _settle_and_watch(self, watch: bool, restore_to) -> None:
        deadline = time.time() + SETTLE_SECONDS
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                return
            if watch and restore_to and _frontmost_name() == THINGS_FRONT_NAME:
                self._last_steal_ts = time.time()
                _log(f"focus steal detected mid-settle; restoring {restore_to}")
                _activate(restore_to)
            time.sleep(min(FRONT_SAMPLE_INTERVAL, remaining))

    def _open_json(self, operations) -> None:
        watch, restore_to = self._capture()
        data = quote(json.dumps(operations))
        url = f"things:///json?auth-token={quote(self.token_provider())}&data={data}"
        subprocess.run(["open", "-g", url], check=True, timeout=15)
        self._settle_and_watch(watch, restore_to)

    # -- ThingsWriter interface --------------------------------------------
    def create(self, envelope: dict, provenance_tag: str, idem_key=None) -> None:
        # idem_key unused: locally there's no queue to dedupe at; the
        # SpokeCore journal is the no-dup guard on this path.
        attrs = {
            "title": envelope["title"],
            "notes": envelope.get("notes") or "",
            "tags": [provenance_tag],
        }
        if envelope.get("when"):
            attrs["when"] = envelope["when"]
        if envelope.get("deadline"):
            attrs["deadline"] = envelope["deadline"]
        if envelope.get("checklist"):
            attrs["checklist-items"] = [
                {"type": "checklist-item", "attributes": {"title": t}}
                for t in envelope["checklist"]
            ]
        self._open_json([{"type": "to-do", "operation": "create",
                          "attributes": attrs}])

    def set_terminal(self, uuid: str, state: str) -> bool:
        attr = "completed" if state == "completed" else "canceled"
        self._open_json([{"type": "to-do", "operation": "update", "id": uuid,
                          "attributes": {attr: True}}])
        want = "completed" if state == "completed" else "canceled"
        return self._verify(lambda: (self.reader.status(uuid) or {}).get("status") == want)

    def set_tags(self, uuid: str, tags) -> bool:
        tags = list(tags)
        self._open_json([{"type": "to-do", "operation": "update", "id": uuid,
                          "attributes": {"tags": tags}}])
        want = set(tags)
        return self._verify(
            lambda: set(self.reader.tags_of(uuid) or []) == want)

    def _verify(self, check) -> bool:
        """URL applies are async fire-and-forget — never trust `open`
        returning. Bounded read-back loop against the local mirror."""
        deadline = time.time() + VERIFY_TIMEOUT
        while time.time() < deadline:
            self.reader.refresh()
            try:
                if check():
                    return True
            except Exception:
                pass
            time.sleep(VERIFY_INTERVAL)
        return False
