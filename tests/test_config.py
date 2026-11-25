import json
import tempfile
import unittest
from pathlib import Path

from bandar.core import config as cfg
from tests.helpers import service


class NormalizeTests(unittest.TestCase):
    def test_empty_input_gives_complete_defaults(self):
        config = cfg.normalize(None)
        self.assertEqual(config["settings"], cfg.DEFAULT_SETTINGS)
        self.assertEqual(config["services"], [])
        self.assertEqual(config["session"], {"running": []})

    def test_bad_fields_are_repaired_independently(self):
        config = cfg.normalize(
            {
                "settings": {
                    "theme": "neon",
                    "language": "fa",
                    "maxRetries": "x",
                    "startTimeout": 1,
                },
                "services": [
                    service(name="a", kind="deploy", address="not an ip"),
                    service(name="", target="x"),  # unusable: no name
                    service(name="b", localPort=0),  # unusable: bad port
                ],
            }
        )
        self.assertEqual(config["settings"]["theme"], "auto")
        self.assertEqual(config["settings"]["language"], "fa")
        self.assertEqual(config["settings"]["maxRetries"], 0)
        self.assertEqual(config["settings"]["startTimeout"], 5)
        self.assertEqual(len(config["services"]), 1)
        self.assertEqual(config["services"][0]["kind"], "deployment")
        self.assertEqual(config["services"][0]["address"], "127.0.0.1")

    def test_duplicate_names_and_ids_are_made_unique(self):
        config = cfg.normalize({"services": [service(name="db"), service(name="DB", localPort=1)]})
        names = [s["name"] for s in config["services"]]
        ids = {s["id"] for s in config["services"]}
        self.assertEqual(names, ["db", "DB-2"])
        self.assertEqual(len(ids), 2)

    def test_group_may_be_referenced_by_name_in_hand_edited_files(self):
        config = cfg.normalize(
            {"groups": [{"id": "g_1", "name": "Orders"}], "services": [service(group="orders")]}
        )
        self.assertEqual(config["services"][0]["group"], "g_1")

    def test_group_environment_is_validated(self):
        config = cfg.normalize(
            {
                "groups": [
                    {"name": "a", "environment": "staging"},
                    {"name": "b", "environment": "moon"},
                ]
            }
        )
        self.assertEqual([g["environment"] for g in config["groups"]], ["staging", ""])

    def test_unknown_group_and_session_entries_are_dropped(self):
        config = cfg.normalize(
            {"services": [service(group="nope")], "session": {"running": ["s_test", "ghost"]}}
        )
        self.assertEqual(config["services"][0]["group"], "")
        self.assertEqual(config["session"]["running"], ["s_test"])

    def test_settings_from_version_1_0_are_migrated(self):
        old = cfg.normalize_settings({"notifications": False, "closeToTray": False})
        self.assertEqual((old["notifications"], old["closeAction"]), ("off", "quit"))
        fresh = cfg.normalize_settings({"notifications": True})
        self.assertEqual((fresh["notifications"], fresh["closeAction"]), ("always", "ask"))
        self.assertEqual(cfg.normalize_settings({"language": "ar"})["language"], "ar")

    def test_the_list_view_is_remembered_and_validated(self):
        config = cfg.normalize(
            {
                "groups": [{"id": "g_1", "name": "gold"}],
                "settings": {"view": "pinned", "viewGroup": "g_1", "viewEnv": "staging"},
            }
        )
        self.assertEqual(
            [config["settings"][k] for k in ("view", "viewGroup", "viewEnv")],
            ["pinned", "g_1", "staging"],
        )
        stale = cfg.normalize(
            {"settings": {"view": "nonsense", "viewGroup": "g_gone", "viewEnv": "moon"}}
        )
        self.assertEqual(
            [stale["settings"][k] for k in ("view", "viewGroup", "viewEnv")], ["all", "", ""]
        )
        ungrouped = cfg.normalize({"settings": {"viewGroup": "__ungrouped__"}})
        self.assertEqual(ungrouped["settings"]["viewGroup"], "__ungrouped__")

    def test_kubeconfig_location(self):
        home = Path.home()
        self.assertEqual(cfg.kubeconfig_path({}, {}), home / ".kube" / "config")
        self.assertEqual(cfg.kubeconfig_path({}, {"KUBECONFIG": "/a:/b"}), Path("/a"))
        self.assertEqual(
            cfg.kubeconfig_path({"kubeconfig": "~/k"}, {"KUBECONFIG": "/a"}), home / "k"
        )

    def test_health_check_interval_has_a_floor(self):
        self.assertEqual(
            cfg.normalize_settings({"healthCheckInterval": 2})["healthCheckInterval"], 5
        )
        self.assertEqual(
            cfg.normalize_settings({"healthCheckInterval": 0})["healthCheckInterval"], 0
        )


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.config = cfg.normalize({"services": [service(id="s_a", name="alpha", localPort=5432)]})

    def valid(self, **changes):
        data = {
            "name": "beta",
            "context": "",
            "namespace": "",
            "kind": "service",
            "target": "db",
            "localPort": "6000",
            "remotePort": "5432",
            "address": "",
            "extraArgs": "--pod-running-timeout=1m",
        }
        data.update(changes)
        return data

    def test_valid_service_is_completed(self):
        result, errors = cfg.validate_service(self.valid(), self.config)
        self.assertEqual(errors, {})
        self.assertEqual(result["localPort"], 6000)
        self.assertEqual(result["address"], "127.0.0.1")
        self.assertEqual(result["extraArgs"], ["--pod-running-timeout=1m"])
        self.assertTrue(result["id"].startswith("s_"))

    def test_each_field_reports_its_own_error(self):
        _, errors = cfg.validate_service(
            self.valid(
                name="Alpha",
                namespace="Bad_NS",
                target="Bad Name",
                localPort="70000",
                remotePort="",
                address="nowhere",
                extraArgs="positional",
            ),
            self.config,
        )
        self.assertEqual(errors["name"]["code"], "duplicate_service")
        self.assertEqual(errors["namespace"]["code"], "invalid_namespace")
        self.assertEqual(errors["target"]["code"], "invalid_target")
        self.assertEqual(errors["localPort"]["code"], "invalid_port")
        self.assertEqual(errors["remotePort"]["code"], "invalid_remote_port")
        self.assertEqual(errors["address"]["code"], "invalid_address")
        self.assertEqual(errors["extraArgs"]["code"], "args_must_be_flags")

    def test_local_port_belongs_to_one_service_even_when_stopped(self):
        _, errors = cfg.validate_service(self.valid(localPort=5432), self.config)
        self.assertEqual(errors["localPort"], {"code": "port_taken", "service": "alpha"})

    def test_editing_keeps_its_own_port_and_id(self):
        result, errors = cfg.validate_service(
            self.valid(name="alpha", localPort=5432), self.config, editing="s_a"
        )
        self.assertEqual(errors, {})
        self.assertEqual(result["id"], "s_a")

    def test_different_bind_addresses_may_share_a_port(self):
        _, errors = cfg.validate_service(
            self.valid(localPort=5432, address="127.0.0.2"), self.config
        )
        self.assertNotIn("localPort", errors)
        _, errors = cfg.validate_service(self.valid(localPort=5432, address="0.0.0.0"), self.config)
        self.assertEqual(errors["localPort"]["code"], "port_taken")

    def test_named_remote_ports_are_accepted(self):
        result, errors = cfg.validate_service(self.valid(remotePort="http"), self.config)
        self.assertEqual(errors, {})
        self.assertEqual(result["remotePort"], "http")

    def test_group_names_are_unique_case_insensitively(self):
        config = cfg.normalize({"groups": [{"id": "g_1", "name": "Orders"}]})
        _, errors = cfg.validate_group({"name": "orders"}, config)
        self.assertEqual(errors["name"]["code"], "duplicate_group")
        group, errors = cfg.validate_group(
            {"name": "orders", "color": "red"}, config, editing="g_1"
        )
        self.assertEqual((errors, group["color"]), ({}, "red"))


class OrderingTests(unittest.TestCase):
    items = [{"id": i, "name": n} for i, n in (("1", "c"), ("2", "a"), ("3", "b"))]

    def test_move_before_and_to_end(self):
        self.assertEqual([i["id"] for i in cfg.move_before(self.items, "3", "1")], ["3", "1", "2"])
        self.assertEqual([i["id"] for i in cfg.move_before(self.items, "1", None)], ["2", "3", "1"])

    def test_sort_subset_keeps_other_positions(self):
        ordered = cfg.sorted_by_name(self.items, ids={"1", "3"})
        self.assertEqual([i["name"] for i in ordered], ["b", "a", "c"])
        self.assertEqual([i["name"] for i in cfg.sorted_by_name(self.items)], ["a", "b", "c"])


class FileTests(unittest.TestCase):
    def test_invalid_json_is_reported_and_left_untouched(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            path.write_text("{ broken")
            config, notice = cfg.load(path)
            self.assertEqual(config, cfg.empty())
            self.assertEqual(notice["code"], "config_invalid")
            self.assertTrue(notice["readOnly"])
            self.assertEqual(path.read_text(), "{ broken")

    def test_atomic_write_round_trip_is_private(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "nested" / "config.json"
            config = cfg.normalize({"services": [service()]})
            cfg.write_atomic(path, cfg.dumps(config))
            self.assertEqual(cfg.load(path), (config, None))
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(path.read_text())["version"], cfg.SCHEMA)


if __name__ == "__main__":
    unittest.main()
