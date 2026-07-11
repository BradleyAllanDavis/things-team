"""LocalWriter must never let a things:// auth-token leak into an
exception message — CalledProcessError/TimeoutExpired from `open -g`
embed the full argv (including the url) by default, and that string
ends up in spoke logs and in the hub nack payload (core.py)."""

import subprocess
import unittest
from unittest import mock

from spoke.writer_local import LocalWriter

SECRET_TOKEN = "super-secret-things-token"


class FakeReader:
    def refresh(self):
        pass

    def status(self, uuid):
        return {"status": "open"}

    def tags_of(self, uuid):
        return []


class TokenRedactionTests(unittest.TestCase):
    def setUp(self):
        self.writer = LocalWriter(lambda: SECRET_TOKEN, FakeReader())

    def test_called_process_error_does_not_leak_token(self):
        with mock.patch(
            "subprocess.run",
            side_effect=subprocess.CalledProcessError(
                1, ["open", "-g", f"things:///json?auth-token={SECRET_TOKEN}&data=x"]),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                self.writer.create({"title": "t"}, "from-bradley")
        self.assertNotIn(SECRET_TOKEN, str(ctx.exception))
        self.assertNotIn("auth-token", str(ctx.exception))

    def test_timeout_expired_does_not_leak_token(self):
        with mock.patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(
                ["open", "-g", f"things:///json?auth-token={SECRET_TOKEN}&data=x"], 15),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                self.writer.create({"title": "t"}, "from-bradley")
        self.assertNotIn(SECRET_TOKEN, str(ctx.exception))
        self.assertNotIn("auth-token", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
