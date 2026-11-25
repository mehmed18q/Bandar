import unittest

from bandar.core import config as cfg
from bandar.core.commands import (
    CommandError,
    apply_import,
    build_args,
    export_text,
    parse_kubectl,
    plan_import,
)
from tests.helpers import service


class ParseTests(unittest.TestCase):
    def test_full_command(self):
        fields = parse_kubectl(
            "kubectl --context main -n orders-api port-forward svc/psql-master 5433:5432"
        )
        self.assertEqual(
            fields,
            {
                "context": "main",
                "namespace": "orders-api",
                "kind": "service",
                "target": "psql-master",
                "localPort": 5433,
                "remotePort": 5432,
                "address": "127.0.0.1",
                "extraArgs": [],
            },
        )

    def test_flag_spellings(self):
        fields = parse_kubectl(
            "/usr/local/bin/kubectl port-forward --context=prod -nchat deploy/api 8080 "
            "--address 0.0.0.0 --pod-running-timeout=2m --kubeconfig /tmp/k"
        )
        self.assertEqual(fields["context"], "prod")
        self.assertEqual(fields["namespace"], "chat")
        self.assertEqual(fields["kind"], "deployment")
        self.assertEqual((fields["localPort"], fields["remotePort"]), (8080, 8080))
        self.assertEqual(fields["address"], "0.0.0.0")
        self.assertEqual(
            fields["extraArgs"], ["--pod-running-timeout=2m", "--kubeconfig", "/tmp/k"]
        )

    def test_bare_name_is_a_pod_and_named_ports_work(self):
        fields = parse_kubectl("kubectl port-forward my-pod 9000:http")
        self.assertEqual(
            (fields["kind"], fields["target"], fields["remotePort"]), ("pod", "my-pod", "http")
        )

    def test_errors_have_codes(self):
        cases = {
            "kubectl get pods": "not_port_forward",
            "kubectl port-forward": "missing_target",
            "kubectl port-forward svc/x": "missing_ports",
            "kubectl port-forward svc/x 1:2 3:4": "multiple_ports",
            "kubectl port-forward svc/x :5432": "random_local_port",
            "kubectl port-forward svc/x 99999:1": "invalid_port_spec",
            "kubectl port-forward cronjob/x 1:2": "unsupported_kind",
            "kubectl port-forward svc/x 1:2 --context": "missing_flag_value",
            "kubectl port-forward 'svc/x 1:2": "unbalanced_quotes",
        }
        for command, code in cases.items():
            with self.subTest(command=command), self.assertRaises(CommandError) as caught:
                parse_kubectl(command)
            self.assertEqual(caught.exception.code, code)

    def test_build_args_round_trips_through_the_parser(self):
        original = service(extraArgs=["--pod-running-timeout=1m"])
        args = build_args(original, {"kubeconfig": ""})
        self.assertEqual(args[:4], ["--context", "main", "--namespace", "default"])
        parsed = parse_kubectl(["kubectl", *args])
        for key in ("context", "namespace", "kind", "target", "localPort", "remotePort", "address"):
            self.assertEqual(parsed[key], original[key], key)


LIST = """
# comment
[orders]
orders-db = kubectl --context main -n orders port-forward svc/psql 5432:5432
orders-cache: kubectl --context main -n orders port-forward svc/redis 6379:6379
[]
kubectl -n chat port-forward svc/chat-redis 6381:6379
=====
this is not a command
dup = kubectl port-forward svc/other 6379:1
"""


class ImportTests(unittest.TestCase):
    def test_plan_reports_every_line(self):
        plan = plan_import(LIST, cfg.empty())
        actions = [(line.line, line.action, line.name) for line in plan.lines]
        self.assertEqual(
            actions,
            [
                (3, "group", "orders"),
                (4, "add", "orders-db"),
                (5, "add", "orders-cache"),
                (6, "group", ""),
                (7, "add", "chat-redis"),
                (9, "error", ""),
                (10, "error", "dup"),
            ],
        )
        self.assertEqual(plan.lines[0].detail["count"], 2)
        self.assertEqual(plan.lines[-1].detail, {"code": "port_taken", "service": "orders-cache"})

    def test_apply_creates_groups_and_keeps_input_untouched(self):
        base = cfg.empty()
        config, changed = apply_import(plan_import(LIST, base), base)
        self.assertEqual(base, cfg.empty())
        self.assertEqual(len(changed), 3)
        groups = {g["name"]: g["id"] for g in config["groups"]}
        membership = {s["name"]: s["group"] for s in config["services"]}
        self.assertEqual(
            membership,
            {"orders-db": groups["orders"], "orders-cache": groups["orders"], "chat-redis": ""},
        )

    def test_existing_services_update_or_skip(self):
        config, _ = apply_import(plan_import(LIST, cfg.empty()), cfg.empty())
        change = "orders-db = kubectl --context prod -n orders port-forward svc/psql 5432:5432"
        plan = plan_import(change, config, update_existing=True)
        self.assertEqual(plan.lines[0].action, "update")
        updated, _ = apply_import(plan, config)
        db = next(s for s in updated["services"] if s["name"] == "orders-db")
        self.assertEqual(db["context"], "prod")
        self.assertEqual(db["group"], next(g["id"] for g in updated["groups"]), "group kept")
        self.assertEqual(plan_import(change, config, update_existing=False).lines[0].action, "skip")

    def test_group_headers_carry_the_environment(self):
        text = (
            "[orders-stage @staging]\nstage-db = kubectl port-forward svc/db 5433:5432\n[x @nope]\n"
        )
        plan = plan_import(text, cfg.empty())
        self.assertEqual(plan.lines[0].detail["env"], "staging")
        self.assertEqual(plan.lines[-1].detail, {"code": "unknown_environment", "env": "nope"})
        config, _ = apply_import(plan, cfg.empty())
        self.assertEqual(config["groups"][0]["environment"], "staging")
        self.assertIn("[orders-stage @staging]", export_text(config))

    def test_export_then_import_is_lossless(self):
        config, _ = apply_import(plan_import(LIST, cfg.empty()), cfg.empty())
        text = export_text(config, header="test")
        again, _ = apply_import(plan_import(text, cfg.empty()), cfg.empty())
        strip = lambda c: sorted(  # noqa: E731
            (s["name"], s["target"], s["localPort"], s["context"], s["namespace"])
            for s in c["services"]
        )
        self.assertEqual(strip(again), strip(config))
        self.assertEqual([g["name"] for g in again["groups"]], ["orders"])


if __name__ == "__main__":
    unittest.main()
