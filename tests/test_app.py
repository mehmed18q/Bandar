"""Application service: every user intention, persisted and validated."""

import json
import socket
import tempfile
import unittest
from pathlib import Path

from bandar.app import Application
from bandar.core import config as cfg
from tests.helpers import qt, settings, wait_until


def call(method, params):
    """Run an asynchronous Application method and wait for its reply."""
    replies = []
    method(params, replies.append)
    wait_until(lambda: replies)
    return replies[0]


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        qt()
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "config.json"
        config = cfg.empty()
        config["settings"] = settings()
        self.path.write_text(cfg.dumps(config))
        self.app = Application(self.path)

    def tearDown(self):
        self.app.shutdown()
        self.folder.cleanup()

    def saved(self):
        wait_until(lambda: json.loads(self.path.read_text()) == self.app.config, 4)
        return json.loads(self.path.read_text())

    def add(self, name, port, **extra):
        data = {
            "name": name,
            "kind": "service",
            "target": "ok-db",
            "localPort": port,
            "remotePort": 5432,
        }
        data.update(extra)
        return call(self.app.save_service, {"data": data})

    def test_add_edit_and_delete_are_persisted(self):
        result = self.add("db", 47701)
        self.assertTrue(result["ok"])
        sid = result["id"]
        self.assertEqual(self.saved()["services"][0]["name"], "db")
        edited = call(
            self.app.save_service,
            {"id": sid, "data": {**self.app.config["services"][0], "name": "main-db"}},
        )
        self.assertTrue(edited["ok"])
        self.assertEqual(self.saved()["services"][0]["name"], "main-db")
        self.app.delete_services({"ids": [sid]})
        self.assertEqual(self.saved()["services"], [])

    def test_port_of_a_stopped_service_cannot_be_reused(self):
        self.add("db", 47702)
        result = self.add("other", 47702)
        self.assertFalse(result["ok"])
        self.assertEqual(result["errors"]["localPort"], {"code": "port_taken", "service": "db"})

    def test_port_busy_on_this_machine_is_rejected_with_its_owner(self):
        blocker = socket.socket()
        blocker.bind(("127.0.0.1", 47703))
        blocker.listen()
        try:
            result = self.add("db", 47703)
            self.assertFalse(result["ok"])
            self.assertEqual(result["errors"]["localPort"]["code"], "port_busy")
            self.assertIsNotNone(result["errors"]["localPort"]["owner"]["pid"])
            check = call(self.app.check_port, {"port": 47703})
            self.assertEqual(check["status"], "busy")
        finally:
            blocker.close()

    def test_groups_membership_order_and_deletion(self):
        a = self.add("a", 47711)["id"]
        b = self.add("b", 47712)["id"]
        group = self.app.save_group(
            {"data": {"name": "orders", "color": "amber"}, "services": [a, b]}
        )
        gid = group["id"]
        self.assertEqual({s["group"] for s in self.app.config["services"]}, {gid})
        self.app.move_service({"id": b, "group": gid, "before": a})
        self.assertEqual([s["name"] for s in self.app.config["services"]], ["b", "a"])
        self.app.sort_services({"group": gid})
        self.assertEqual([s["name"] for s in self.app.config["services"]], ["a", "b"])
        self.app.delete_group({"id": gid, "withServices": False})
        self.assertEqual({s["group"] for s in self.saved()["services"]}, {""})
        gid = self.app.save_group({"data": {"name": "temp"}, "services": [a]})["id"]
        self.app.delete_group({"id": gid, "withServices": True})
        self.assertEqual([s["name"] for s in self.saved()["services"]], ["b"])

    def test_running_services_are_remembered_for_the_next_launch(self):
        sid = self.add("db", 47721)["id"]
        self.app.start({"ids": [sid]})
        wait_until(lambda: self.app.manager.get(sid).state == "healthy")
        self.assertEqual(self.saved()["session"]["running"], [sid])
        self.app.shutdown()
        restarted = Application(self.path)
        try:
            restarted.boot()
            self.assertTrue(wait_until(lambda: restarted.manager.get(sid).state == "healthy"))
        finally:
            restarted.shutdown()

    def test_import_then_export(self):
        text = "[orders]\ndb = kubectl -n orders port-forward svc/ok-db 47731:5432\n"
        preview = self.app.preview_import({"text": text})
        self.assertEqual(preview["summary"], {"group": 1, "add": 1})
        self.assertTrue(self.app.apply_import({"text": text})["ok"])
        self.assertIn(
            "[orders]\ndb = kubectl --namespace orders port-forward svc/ok-db 47731:5432",
            self.app.export({})["text"],
        )

    def test_switching_the_current_context(self):
        self.app.refresh_contexts()
        wait_until(lambda: self.app.kube_info["contexts"])
        self.assertEqual(self.app.kube_info["current"], "main")
        result = call(self.app.use_context, {"name": "stage"})
        self.assertTrue(result["ok"])
        self.assertEqual(self.app.kube_info["current"], "stage")
        refused = call(self.app.use_context, {"name": "nowhere"})
        self.assertEqual(refused["error"]["code"], "context_missing")

    def test_failures_and_recoveries_are_announced(self):
        notices = []
        self.app.notice.connect(notices.append)
        sid = self.add("db", 47751, target="auth-db")["id"]
        self.app.start({"ids": [sid]})
        self.assertTrue(wait_until(lambda: notices))
        self.assertEqual(notices[0]["code"], "forward_failed")
        self.assertEqual(notices[0]["kind"], "failed")
        self.assertEqual(notices[0]["error"]["code"], "auth")

    def test_external_edits_reload_and_invalid_edits_pause_saving(self):
        self.add("db", 47741)
        self.saved()
        changed = json.loads(self.path.read_text())
        changed["services"][0]["name"] = "edited-by-hand"
        self.path.write_text(json.dumps(changed))
        self.assertTrue(
            wait_until(lambda: self.app.config["services"][0]["name"] == "edited-by-hand", 5)
        )
        self.path.write_text("{ not json")
        self.assertTrue(wait_until(lambda: self.app.store.read_only, 5))
        self.app.update_settings({"theme": "dark"})
        wait_until(lambda: False, 0.5)
        self.assertEqual(
            self.path.read_text(), "{ not json", "a broken hand edit is never overwritten"
        )


if __name__ == "__main__":
    unittest.main()
