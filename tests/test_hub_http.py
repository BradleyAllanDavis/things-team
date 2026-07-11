"""HttpHubClient must never follow a redirect — the default urllib opener
resends every header (including the Bearer device token) to wherever
`Location` points, which would hand the token to an attacker-controlled
host reached via a compromised/MITM'd hub."""

import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from spoke.hub_http import HttpHubClient, HubHTTPError

SECRET_TOKEN = "device-token-should-never-leave-the-hub-host"


class _Attacker(BaseHTTPRequestHandler):
    """Records whether it was ever hit, and with what Authorization header."""

    requests = []

    def do_GET(self):
        _Attacker.requests.append(self.headers.get("Authorization"))
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args):
        pass


def _make_redirector(target_url):
    class _Redirector(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302)
            self.send_header("Location", target_url)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            pass

    return _Redirector


class RedirectRefusalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _Attacker.requests = []
        cls.attacker = HTTPServer(("127.0.0.1", 0), _Attacker)
        cls.attacker_port = cls.attacker.server_address[1]
        threading.Thread(target=cls.attacker.serve_forever, daemon=True).start()

        redirector = _make_redirector(f"http://127.0.0.1:{cls.attacker_port}/steal")
        cls.hub = HTTPServer(("127.0.0.1", 0), redirector)
        cls.hub_port = cls.hub.server_address[1]
        threading.Thread(target=cls.hub.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.hub.shutdown()
        cls.attacker.shutdown()

    def test_redirect_is_refused_and_token_never_reaches_attacker(self):
        client = HttpHubClient(f"http://127.0.0.1:{self.hub_port}",
                                lambda: SECRET_TOKEN)
        with self.assertRaises((HubHTTPError, Exception)):
            client.health()
        self.assertEqual(_Attacker.requests, [],
                          "the redirect target must never be contacted")


if __name__ == "__main__":
    unittest.main()
