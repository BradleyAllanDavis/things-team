"""HubClient over HTTP — what a real (remote) spoke uses to talk to the
things-team hub. Stdlib urllib, hub addressed BY IP in deployed configs
(LaunchAgent-context DNS for LAN hostnames is unreliable on macOS — a
hard-won lesson from the predecessor system).

Python 3.9-compatible, stdlib only.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request


class HubHTTPError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"hub returned {status}: {body}")
        self.status = status


class HttpHubClient:
    def __init__(self, hub_url: str, token_provider, timeout: float = 40.0,
                 poll_wait: float = 0.0):
        self.hub_url = hub_url.rstrip("/")
        self.token_provider = token_provider  # callable -> str
        self.timeout = timeout
        self.poll_wait = poll_wait  # >0 turns delivery polls into long-polls

    def _request(self, method: str, path: str, body=None, timeout=None):
        url = f"{self.hub_url}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.token_provider()}")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:  # surface hub's error payload
            raise HubHTTPError(exc.code, exc.read().decode("utf-8", "replace"))

    # -- HubClient interface -----------------------------------------------
    def push_transfer(self, to: str, src_uuid: str, payload: dict, rev: int = 1) -> dict:
        return self._request("POST", "/v1/transfers", {
            "to": to, "src_uuid": src_uuid, "payload": payload, "rev": rev})

    def deliveries(self, limit: int = 10) -> list:
        resp = self._request(
            "GET", f"/v1/deliveries?limit={limit}&wait={self.poll_wait}",
            timeout=self.timeout + self.poll_wait)
        return resp.get("deliveries", [])

    def ack(self, delivery_id: str, dst_uuid=None) -> dict:
        body = {"dst_uuid": dst_uuid} if dst_uuid else {}
        return self._request("POST", f"/v1/deliveries/{delivery_id}/ack", body)

    def nack(self, delivery_id: str, error: str) -> dict:
        return self._request("POST", f"/v1/deliveries/{delivery_id}/nack",
                             {"error": error})

    def watch(self) -> list:
        return self._request("GET", "/v1/watch").get("watch", [])

    def observe(self, transfer_id: str, state: str) -> dict:
        return self._request("POST", "/v1/observations",
                             {"transfer_id": transfer_id, "state": state})

    def health(self) -> dict:
        return self._request("GET", "/v1/health")
