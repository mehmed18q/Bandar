"""The forward state machine against a real (fake) kubectl process."""

import socket
import tempfile
import unittest
from pathlib import Path

from bandar.runtime.forward import Forward, State
from bandar.runtime.manager import ForwardManager
from bandar.runtime.tasks import TaskRunner
from tests.helpers import qt, service, settings, wait_until


class ForwardTests(unittest.TestCase):
    def setUp(self):
        qt()
        self.tasks = TaskRunner()
        self.values = settings()
        self.forwards = []

    def tearDown(self):
        for forward in self.forwards:
            forward.stop()
        wait_until(lambda: all(f.state == State.STOPPED for f in self.forwards), 6)
        self.tasks.shutdown()

    def make(self, **overrides):
        forward = Forward(service(**overrides), lambda: self.values, self.tasks)
        self.forwards.append(forward)
        return forward

    def test_becomes_healthy_and_accepts_connections(self):
        forward = self.make(target="ok-db", localPort=25601)
        forward.start()
        self.assertEqual(forward.state, State.STARTING)
        self.assertTrue(wait_until(lambda: forward.state == State.HEALTHY))
        with socket.create_connection(("127.0.0.1", 25601), timeout=2):
            pass
        self.assertTrue(wait_until(lambda: forward.connections == 1))
        self.assertIsNotNone(forward.snapshot()["healthySince"])
        self.assertTrue(any(e["level"] == "cmd" for e in forward.logs))

    def test_authorization_error_is_not_retried(self):
        forward = self.make(target="auth-db", localPort=25602)
        forward.start()
        self.assertTrue(wait_until(lambda: forward.state == State.ERROR))
        self.assertEqual(forward.error["code"], "auth")
        self.assertFalse(forward.error["retryable"])
        self.assertTrue(forward.desired, "an error keeps the intention to run")

    def test_lost_connection_is_retried_with_backoff(self):
        forward = self.make(target="flaky-db", localPort=25603)
        failures = []
        forward.failed.connect(lambda _id, snapshot: failures.append(snapshot))
        forward.start()
        self.assertTrue(wait_until(lambda: forward.state == State.RETRYING))
        self.assertEqual(forward.error["code"], "connection_lost")
        self.assertEqual(forward.attempt, 1)
        self.assertTrue(wait_until(lambda: forward.restarts >= 1 and forward.attempt >= 2, 10))
        self.assertGreaterEqual(len(failures), 2)

    def test_recovers_after_a_transient_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            import os

            os.environ["FAKE_KUBECTL_MARKER"] = os.path.join(folder, "marker")
            forward = self.make(target="once-flaky-db", localPort=25604)
            forward.start()
            self.assertTrue(wait_until(lambda: forward.state == State.RETRYING))
            self.assertTrue(wait_until(lambda: forward.state == State.HEALTHY, 10))
            self.assertIsNone(forward.error)
            self.assertEqual(forward.last_error["code"], "connection_lost")
            self.assertEqual(forward.restarts, 1)

    def test_busy_port_fails_before_launch_and_names_the_owner(self):
        blocker = socket.socket()
        blocker.bind(("127.0.0.1", 25605))
        blocker.listen()
        try:
            forward = self.make(localPort=25605)
            forward.start()
            self.assertEqual(forward.state, State.ERROR)
            self.assertEqual(forward.error["code"], "port_in_use")
            self.assertTrue(wait_until(lambda: "owner" in forward.error))
            self.assertFalse(forward.error["owner"]["ours"])
        finally:
            blocker.close()

    def test_start_timeout(self):
        self.values = settings(startTimeout=1, autoRetry=False)
        forward = self.make(target="slow-db", localPort=25606)
        forward.start()
        self.assertTrue(wait_until(lambda: forward.state == State.ERROR, 6))
        self.assertEqual(forward.error["code"], "start_timeout")

    def test_missing_kubectl(self):
        self.values = settings(kubectl="/nonexistent/kubectl")
        forward = self.make(localPort=25607)
        forward.start()
        self.assertTrue(wait_until(lambda: forward.state == State.ERROR))
        self.assertEqual(forward.error["code"], "kubectl_missing")

    def test_stop_frees_the_port_and_clears_errors(self):
        forward = self.make(target="ok-db", localPort=25608)
        forward.start()
        self.assertTrue(wait_until(lambda: forward.state == State.HEALTHY))
        forward.stop()
        self.assertEqual(forward.state, State.STOPPING)
        self.assertTrue(wait_until(lambda: forward.state == State.STOPPED))
        self.assertFalse(forward.desired)
        probe = socket.socket()
        probe.bind(("127.0.0.1", 25608))
        probe.close()

    def test_editing_the_command_reconnects_without_counting_a_restart(self):
        forward = self.make(target="ok-db", localPort=25609)
        forward.start()
        self.assertTrue(wait_until(lambda: forward.state == State.HEALTHY))
        forward.reconfigure(service(target="ok-db", localPort=25610))
        self.assertTrue(wait_until(lambda: forward.state == State.HEALTHY and forward.pid))
        self.assertEqual(forward.restarts, 0)
        with socket.create_connection(("127.0.0.1", 25610), timeout=2):
            pass

    def test_warning_keeps_the_tunnel_healthy(self):
        forward = self.make(target="warn-db", localPort=25611)
        forward.start()
        self.assertTrue(wait_until(lambda: forward.warning is not None))
        self.assertEqual(forward.state, State.HEALTHY)
        self.assertEqual(forward.warning["code"], "remote_refused")


class OrphanTests(unittest.TestCase):
    def test_kubectl_dies_with_its_parent(self):
        """Even a crashed (SIGKILLed) Bandar leaves no port-forward behind."""
        import os
        import signal
        import subprocess
        import sys
        import textwrap

        from bandar.runtime.forward import DEATH_WRAPPER

        if not DEATH_WRAPPER:
            self.skipTest("setpriv is not available")
        script = textwrap.dedent(
            f"""
            import sys
            sys.path.insert(0, {str(Path(__file__).resolve().parent.parent)!r})
            from tests.helpers import qt, service, settings, wait_until
            from bandar.runtime.forward import Forward
            from bandar.runtime.tasks import TaskRunner
            qt()
            forward = Forward(service(target="ok-orphan", localPort=25690), settings, TaskRunner())
            forward.start()
            wait_until(lambda: forward.state == "healthy")
            print(forward.pid, flush=True)
            import time; time.sleep(60)
            """
        )
        parent = subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE, text=True)
        child = int(parent.stdout.readline())
        os.kill(parent.pid, signal.SIGKILL)
        parent.wait()
        self.assertTrue(wait_until(lambda: not Path(f"/proc/{child}").exists(), 5))
        probe = socket.socket()
        probe.bind(("127.0.0.1", 25690))
        probe.close()


class ManagerTests(unittest.TestCase):
    def test_conflicting_local_ports_are_refused(self):
        qt()
        tasks = TaskRunner()
        manager = ForwardManager(lambda: settings(), tasks)
        manager.sync(
            [service(id="s_1", localPort=25620), service(id="s_2", name="b", localPort=25620)]
        )
        manager.start(["s_1", "s_2"])
        self.assertEqual(manager.get("s_2").state, State.ERROR)
        self.assertEqual(manager.get("s_2").error["code"], "port_conflict")
        self.assertTrue(wait_until(lambda: manager.get("s_1").state == State.HEALTHY))
        self.assertEqual(manager.desired_ids(), ["s_1", "s_2"])
        manager.sync([service(id="s_2", name="b", localPort=25620)])  # s_1 removed → stopped
        self.assertIsNone(manager.get("s_1"))
        manager.stop(["s_2"])
        self.assertTrue(wait_until(lambda: manager.counts().get("stopped") == 1))
        self.assertEqual(manager.shutdown(), 0)
        wait_until(lambda: False, 0.5)  # let the retired forward's process exit
        tasks.shutdown()


if __name__ == "__main__":
    unittest.main()
