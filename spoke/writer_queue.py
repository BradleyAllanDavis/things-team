"""ThingsWriter backed by the things-gateway queue (docs/plans/
things-gateway.md in bradley's dotfiles) — the hub-side writer for the
member whose Macs already run the gateway (no dedicated spoke process
anywhere; the existing things-applier on the always-on Mac is the hand).

Every write is: enqueue a Things JSON-Command-Format op (idempotency-key
deduped at the queue) → poll the op record until the applier acks it
(applied / verified / failed). `create` acks carry NO uuid (the applier
can't learn it without an x-callback receiver), so uuid discovery stays
with SpokeCore's correlate step against the synced mirror.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request


def _log(msg: str) -> None:
    print(f"[things-team-qwriter] {msg}", file=sys.stderr, flush=True)


class QueueWriter:
    def __init__(self, queue_url: str, token_provider,
                 ack_timeout: float = 180.0, poll_interval: float = 2.0,
                 agent: str = "things-team-hub"):
        self.queue_url = queue_url.rstrip("/")
        self.token_provider = token_provider  # callable -> str (re-read per call: rotation)
        self.ack_timeout = ack_timeout
        self.poll_interval = poll_interval
        self.agent = agent

    # -- HTTP plumbing ------------------------------------------------------
    def _request(self, method: str, path: str, body=None, timeout: float = 30):
        url = f"{self.queue_url}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.token_provider()}")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())

    def _submit_and_wait(self, operation: dict, idem_key) -> str:
        resp = self._request("POST", "/v1/ops", {
            "agent": self.agent,
            "idempotency_key": idem_key,
            "operation": operation,
        })
        rec = resp["results"][0]
        if "error" in rec:
            raise RuntimeError(f"queue rejected op: {rec['error']}")
        op_id = rec["id"]
        deadline = time.time() + self.ack_timeout
        while time.time() < deadline:
            status = rec.get("status")
            if status in ("applied", "verified"):
                return status
            if status == "failed":
                raise RuntimeError(
                    f"applier failed op {op_id}: {rec.get('detail')}")
            time.sleep(self.poll_interval)
            rec = self._request("GET", f"/v1/ops/{op_id}")
        raise RuntimeError(
            f"op {op_id} not acked within {self.ack_timeout}s "
            f"(status={rec.get('status')}) — applier Mac asleep?")

    # -- ThingsWriter interface --------------------------------------------
    def create(self, envelope: dict, provenance_tag: str, idem_key=None) -> None:
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
        self._submit_and_wait(
            {"type": "to-do", "operation": "create", "attributes": attrs},
            idem_key)

    def set_terminal(self, uuid: str, state: str) -> bool:
        attr = "completed" if state == "completed" else "canceled"
        status = self._submit_and_wait(
            {"type": "to-do", "operation": "update", "id": uuid,
             "attributes": {attr: True}},
            f"things-team-terminal:{uuid}:{state}")
        if status == "applied":
            _log(f"terminal {state} on {uuid} applied but not mirror-verified")
        return True

    def set_tags(self, uuid: str, tags) -> bool:
        self._submit_and_wait(
            {"type": "to-do", "operation": "update", "id": uuid,
             "attributes": {"tags": list(tags)}},
            None)  # retag is computed-from-current-state; no stable idem key
        return True

    def set_tags_and_terminal(self, uuid: str, tags, state: str) -> bool:
        """Combined tags+terminal write in ONE queue round-trip (one
        submit-and-wait-for-verify instead of two sequential ones) -- see
        SpokeCore._retag_sender_copy, the sender-completes-at-send path."""
        attr = "completed" if state == "completed" else "canceled"
        status = self._submit_and_wait(
            {"type": "to-do", "operation": "update", "id": uuid,
             "attributes": {"tags": list(tags), attr: True}},
            None)  # same as set_tags: computed-from-current-state, no idem key
        if status == "applied":
            _log(f"tags+{state} on {uuid} applied but not mirror-verified")
        return True
