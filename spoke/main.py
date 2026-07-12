"""tandem spoke entrypoint — the LaunchAgent on a member's Mac
(Jill's MacBook Air is the only deployed instance; the other member rides
the things-gateway with no spoke at all).

Config: JSON at ~/Library/Application Support/things-team/config.json
(overridable via TANDEM_SPOKE_CONFIG):

  {
    "hub_url": "http://192.168.0.30:8712",          // BY IP (LaunchAgent DNS)
    "device_token_file": "~/.config/things-team/device-token",
    "things_auth_token_file": "~/.config/things-team/things-auth-token",
    "trigger_tags": {"bradley": ["b"]},              // EXACT titles
    "mirror_path": "~/.cache/things-mirror/main.sqlite",
    "mirror_agent": "com.jill.things-mirror",        // kickstart label
    "tick_seconds": 5,
    "poll_wait": 3                                   // long-poll /v1/deliveries
  }

Runs forever (KeepAlive LaunchAgent), one serialized tick per interval.
Python 3.9-compatible, stdlib only — Apple's /usr/bin/python3 suffices.
"""

from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from spoke.core import SpokeCore, SpokeState  # noqa: E402
from spoke.hub_http import HttpHubClient      # noqa: E402
from spoke.things_db import MirrorReader      # noqa: E402
from spoke.writer_local import LocalWriter    # noqa: E402

DEFAULT_CONFIG = "~/Library/Application Support/things-team/config.json"


def _log(msg: str) -> None:
    print(f"[tandem-spoke] {msg}", file=sys.stderr, flush=True)


def _file_token(path: str):
    expanded = os.path.expanduser(path)

    def provider() -> str:
        with open(expanded) as f:
            return f.read().strip()

    return provider


def main() -> None:
    config_path = os.path.expanduser(
        os.environ.get("TANDEM_SPOKE_CONFIG", DEFAULT_CONFIG))
    with open(config_path) as f:
        cfg = json.load(f)

    reader = MirrorReader(
        cfg.get("mirror_path", "~/.cache/things-mirror/main.sqlite"),
        kick_agent=cfg.get("mirror_agent"))
    writer = LocalWriter(
        _file_token(cfg["things_auth_token_file"]), reader)
    hub = HttpHubClient(
        cfg["hub_url"], _file_token(cfg["device_token_file"]),
        poll_wait=float(cfg.get("poll_wait", 0.0)))
    state_path = os.path.expanduser(
        "~/Library/Application Support/things-team/spoke-state.sqlite")
    core = SpokeCore(
        reader=reader, writer=writer, hub=hub,
        state=SpokeState(state_path),
        trigger_tags=cfg.get("trigger_tags", {}))

    tick_seconds = float(cfg.get("tick_seconds", 60))
    poll_wait = float(cfg.get("poll_wait", 0.0))
    _log(f"spoke up: hub={cfg['hub_url']}, triggers={cfg.get('trigger_tags')}, "
         f"poll_wait={poll_wait}")
    backoff = 5
    # Option 1 (push-transport §5): one loop, local phases then a SHORT held
    # inbound long-poll. The hub's delivery CV wakes the poll the instant a
    # delivery lands (near-push inbound), while tick_local runs every ≤poll_wait
    # (outbound/observe stay responsive) — a long held poll in one serial tick
    # would starve them. Keeps the provably-correct single-threaded spoke.
    while True:
        try:
            core.tick_local()
            core.tick_inbound()   # held ≤poll_wait, woken early by the hub CV
            backoff = 5
        except Exception as exc:  # noqa: BLE001 — keep the agent alive
            _log(f"tick error: {exc!r}; backing off {backoff}s")
            time.sleep(min(backoff, 300))
            backoff = min(backoff * 2, 300)
            continue
        # The held inbound poll IS the idle wait when long-polling (returns
        # instantly on a delivery, parks up to poll_wait otherwise). Only add a
        # fixed sleep when long-poll is disabled, preserving the old cadence.
        if poll_wait <= 0:
            time.sleep(tick_seconds)


if __name__ == "__main__":
    main()
