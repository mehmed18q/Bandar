import unittest

from bandar.core.diagnostics import classify, clean_line, runtime_event, summarize
from bandar.runtime.retry import RetryPolicy


class ClassifyTests(unittest.TestCase):
    cases = {
        "Unable to listen on port 5432: Listeners failed to create with the following errors: "
        "[unable to create listener: Error listen tcp4 127.0.0.1:5432: bind: address already in use]\n"
        "error: unable to listen on any of the requested ports: [{5432 5432}]": (
            "port_in_use",
            False,
        ),
        'error: context "nope" does not exist': ("context_missing", False),
        'Error from server (NotFound): namespaces "x" not found': ("namespace_missing", False),
        'Error from server (NotFound): services "db" not found': ("target_missing", False),
        "error: You must be logged in to the server (Unauthorized)": ("auth", False),
        "Error from server (Forbidden): pods is forbidden": ("auth", False),
        "error: unable to forward port because pod is not running. Current status=Pending": (
            "pod_not_ready",
            True,
        ),
        "error: lost connection to pod": ("connection_lost", True),
        "Unable to connect to the server: dial tcp 10.0.0.1:6443: i/o timeout": (
            "api_unreachable",
            True,
        ),
        "error: Service db does not have a service port 1234": ("remote_port_missing", False),
        "something odd happened": ("unknown", True),
    }

    def test_known_kubectl_messages(self):
        for text, expected in self.cases.items():
            with self.subTest(text=text[:50]):
                problem = classify(text)
                self.assertEqual((problem.code, problem.retryable), expected)

    def test_detail_is_the_most_informative_line_without_klog_noise(self):
        line = "E1125 10:00:00.123456   4321 portforward.go:413] lost connection to pod"
        self.assertEqual(clean_line(line), "lost connection to pod")
        self.assertEqual(
            summarize("Forwarding from x\nerror: lost connection to pod\n"),
            "lost connection to pod",
        )

    def test_runtime_events(self):
        refused = (
            "E1125 portforward.go:424] an error occurred forwarding 5432 -> 5432: error forwarding "
            "port 5432 to pod abc: failed to execute portforward in network namespace: "
            "failed to connect to localhost:5432 inside namespace: connect: connection refused"
        )
        kind, problem = runtime_event(refused)
        self.assertEqual((kind, problem.code), ("warning", "remote_refused"))
        kind, problem = runtime_event("error: lost connection to pod")
        self.assertEqual((kind, problem.code), ("fatal", "connection_lost"))
        self.assertIsNone(runtime_event("Handling connection for 5432"))


class RetryPolicyTests(unittest.TestCase):
    def test_backoff_doubles_and_is_capped(self):
        policy = RetryPolicy(max_delay=30, jitter=0)
        self.assertEqual([policy.delay(n) for n in range(1, 8)], [1, 2, 4, 8, 16, 30, 30])

    def test_limits_and_non_retryable_problems(self):
        transient, fatal = classify("error: lost connection to pod"), classify("Unauthorized")
        self.assertTrue(RetryPolicy(max_attempts=0).allows(999, transient))
        self.assertTrue(RetryPolicy(max_attempts=3).allows(3, transient))
        self.assertFalse(RetryPolicy(max_attempts=3).allows(4, transient))
        self.assertFalse(RetryPolicy().allows(1, fatal))
        self.assertFalse(RetryPolicy(enabled=False).allows(1, transient))

    def test_jitter_stays_within_bounds(self):
        policy = RetryPolicy(jitter=0.15)
        self.assertAlmostEqual(policy.delay(3, rng=lambda: 0.0), 3.4)
        self.assertAlmostEqual(policy.delay(3, rng=lambda: 1.0), 4.6)


if __name__ == "__main__":
    unittest.main()
