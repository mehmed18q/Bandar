"""A dropped VPN: kubectl stays silent, the watchdog notices, tunnels retry and recover."""

import os
import tempfile
import unittest
from pathlib import Path

from bandar.runtime.forward import State
from bandar.runtime.manager import ForwardManager
from bandar.runtime.tasks import TaskRunner
from bandar.runtime.watchdog import ClusterWatchdog, NetworkMonitor
from tests.helpers import qt, service, settings, wait_until


class WatchdogTests(unittest.TestCase):
    def setUp(self):
        qt()
        self.folder = tempfile.TemporaryDirectory()
        self.offline = Path(self.folder.name) / "offline"
        os.environ["FAKE_KUBECTL_OFFLINE"] = str(self.offline)
        self.tasks = TaskRunner()
        self.values = settings(clusterCheckInterval=0)
        self.manager = ForwardManager(lambda: self.values, self.tasks)
        self.watchdog = ClusterWatchdog(self.manager, lambda: self.values, monitor=False)
        self.failures, self.recoveries = [], []
        self.manager.failed.connect(lambda sid, snap: self.failures.append(snap))
        self.manager.recovered.connect(lambda sid, snap: self.recoveries.append(snap))

    def tearDown(self):
        self.watchdog.stop()
        self.manager.stop(self.manager.desired_ids())
        wait_until(lambda: not self.manager.contexts_in_use() and self.manager.shutdown() == 0, 5)
        self.tasks.shutdown()
        os.environ.pop("FAKE_KUBECTL_OFFLINE", None)
        self.folder.cleanup()

    def start(self, sid, port, context="main"):
        self.manager.sync(
            [
                *[f.service for f in self.manager._forwards.values()],
                service(id=sid, localPort=port, context=context),
            ]
        )
        self.manager.start([sid])
        self.assertTrue(wait_until(lambda: self.manager.get(sid).state == State.HEALTHY))
        return self.manager.get(sid)

    def check(self):
        self.values = settings(clusterCheckInterval=10)
        self.watchdog.check_now()
        wait_until(lambda: not self.watchdog._probes, 10)

    def test_vpn_drop_is_detected_retried_and_recovered(self):
        forward = self.start("s_vpn", 47801)
        self.offline.write_text("down")
        # kubectl itself notices nothing: the tunnel still looks healthy.
        wait_until(lambda: False, 0.5)
        self.assertEqual(forward.state, State.HEALTHY)
        self.check()
        self.assertTrue(wait_until(lambda: forward.state == State.RETRYING))
        self.assertEqual(forward.error["code"], "api_unreachable")
        self.assertIn("no route to host", forward.error["detail"])
        self.assertEqual(self.watchdog.unreachable, {"main"})
        self.assertEqual(self.failures[0]["state"], "retrying", "the failure is announced")
        # The VPN comes back: the next check retries at once, without waiting for the backoff.
        self.offline.unlink()
        self.check()
        self.assertTrue(wait_until(lambda: forward.state == State.HEALTHY, 6))
        self.assertEqual(self.watchdog.unreachable, set())
        self.assertTrue(self.recoveries, "the recovery is announced")

    def test_a_single_slow_answer_does_not_drop_tunnels(self):
        forward = self.start("s_slow", 47802)
        self.offline.write_text("slow")
        self.check()
        self.assertEqual(forward.state, State.HEALTHY)
        self.check()
        self.assertTrue(wait_until(lambda: forward.state == State.RETRYING))

    def test_only_the_unreachable_context_is_affected(self):
        main = self.start("s_main", 47803, context="main")
        other = self.start("s_other", 47804, context="prod")
        self.offline.write_text("down")
        self.values = settings(clusterCheckInterval=10)
        self.watchdog._probe("prod")
        wait_until(lambda: not self.watchdog._probes, 10)
        self.assertTrue(wait_until(lambda: other.state == State.RETRYING))
        self.assertEqual(main.state, State.HEALTHY)

    def test_tunnels_are_rebuilt_after_the_network_changes(self):
        """A quick drop-and-return (sleep, Wi-Fi, VPN) leaves dead connections behind."""
        forward = self.start("s_change", 47805)
        before = forward.healthy_since
        self.values = settings(clusterCheckInterval=10)
        self.watchdog.network_changed("resumed")
        self.watchdog.check_now()
        wait_until(lambda: not self.watchdog._probes, 10)
        self.assertTrue(
            wait_until(
                lambda: forward.state == State.HEALTHY and forward.healthy_since != before, 6
            )
        )
        self.assertEqual(forward.restarts, 1)
        # Without a new change, the next check leaves the tunnel alone.
        self.check()
        wait_until(lambda: False, 0.5)
        self.assertEqual(forward.restarts, 1)


class NetworkMonitorTests(unittest.TestCase):
    def test_interface_changes_are_reported(self):
        qt()
        states = [("eth0",), ("eth0",), ("eth0", "tun0")]
        monitor = NetworkMonitor(
            interval_ms=20, read=lambda: states.pop(0) if len(states) > 1 else states[0]
        )
        events = []
        monitor.changed.connect(events.append)
        self.assertTrue(wait_until(lambda: events, 2))
        self.assertEqual(events[0], "interfaces")
        monitor.stop()

    def test_waking_from_sleep_is_reported(self):
        qt()
        now = [1000.0]
        monitor = NetworkMonitor(interval_ms=20, read=lambda: (), clock=lambda: now[0])
        events = []
        monitor.changed.connect(events.append)
        now[0] += 600  # ten minutes pass between two ticks: the machine slept
        self.assertTrue(wait_until(lambda: events, 2))
        self.assertEqual(events[0], "resumed")
        monitor.stop()

    def test_container_interfaces_and_ipv6_are_ignored(self):
        from bandar.runtime.watchdog import VIRTUAL

        for name in ("veth12ab", "docker0", "br-5f2c", "virbr0", "lo", "cali123"):
            self.assertTrue(VIRTUAL.match(name), name)
        for name in ("wlp2s0", "eth0", "enp3s0", "tun0", "wg0", "ppp0"):
            self.assertFalse(VIRTUAL.match(name), name)


if __name__ == "__main__":
    unittest.main()
