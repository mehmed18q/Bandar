import os
import socket
import unittest

from bandar.core import ports


class PortTests(unittest.TestCase):
    def setUp(self):
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen()
        self.port = self.listener.getsockname()[1]

    def tearDown(self):
        self.listener.close()

    def test_status_reports_busy_and_free(self):
        self.assertEqual(ports.status(self.port), "busy")
        self.assertFalse(ports.is_free(self.port, "localhost"))
        free = ports.suggest(self.port, set())
        self.assertNotEqual(free, self.port)
        self.assertEqual(ports.status(free), "free")

    def test_privileged_and_foreign_addresses(self):
        if os.geteuid() != 0:
            self.assertEqual(ports.status(80), "denied")
        self.assertEqual(ports.status(self.port + 1, "10.255.255.254"), "unavailable")

    def test_owner_is_this_process_and_never_released(self):
        owner = ports.owner(self.port)
        self.assertEqual(owner["pid"], os.getpid())
        self.assertFalse(owner["ours"])
        result = ports.release(self.port)
        self.assertEqual((result["ok"], result["code"]), (False, "not_kubectl"))
        self.assertEqual(ports.status(self.port), "busy")

    def test_an_outgoing_connection_is_reported_as_the_owner(self):
        client = socket.create_connection(("127.0.0.1", self.port))
        try:
            source = client.getsockname()[1]
            owner = ports.owner(source)
            self.assertEqual((owner["pid"], owner["outgoing"]), (os.getpid(), True))
            self.assertEqual(ports.release(source)["code"], "not_kubectl")
        finally:
            client.close()

    def test_suggest_skips_configured_ports(self):
        free = ports.suggest(self.port + 1, {self.port + 1, self.port + 2})
        self.assertNotIn(free, {self.port, self.port + 1, self.port + 2})


if __name__ == "__main__":
    unittest.main()
