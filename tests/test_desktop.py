"""Desktop integration: taskbar entry, notifications and the close question."""

import os
import stat
import tempfile
import unittest
from pathlib import Path

from bandar import APP_ID
from bandar.integration import desktop_entry, register_source_run
from bandar.ui.notifier import Notifier
from tests.helpers import ROOT, qt, wait_until


class DesktopEntryTests(unittest.TestCase):
    def test_source_runs_register_an_entry_matching_the_application_id(self):
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder)
            self.assertTrue(register_source_run(ROOT, data))
            self.assertFalse(register_source_run(ROOT, data), "second run changes nothing")
            entry = (data / "applications" / f"{APP_ID}.desktop").read_text()
            self.assertIn("Name=Bandar", entry)
            self.assertIn(f"Icon={APP_ID}", entry)
            self.assertIn("StartupWMClass=Bandar", entry)
            self.assertIn(str(ROOT / "bandar.sh"), entry)
            self.assertTrue((data / "icons/hicolor/scalable/apps" / f"{APP_ID}.svg").is_file())

    def test_paths_with_spaces_are_quoted(self):
        self.assertIn(
            "Exec='/opt/my apps/bandar.sh'", desktop_entry(Path("/opt/my apps/bandar.sh"))
        )


class NotifierTests(unittest.TestCase):
    def setUp(self):
        qt()
        self.folder = tempfile.TemporaryDirectory()
        self.log = Path(self.folder.name) / "calls"
        self.program = Path(self.folder.name) / "notify-send"
        self.program.write_text(
            f'#!/bin/sh\nprintf \'%s\\n\' "$@" >> {self.log}\necho "${{FAKE_ACTION:-}}"\n'
        )
        self.program.chmod(self.program.stat().st_mode | stat.S_IEXEC)

    def tearDown(self):
        self.folder.cleanup()
        os.environ.pop("FAKE_ACTION", None)

    def test_notifications_are_sent_with_actions_and_throttled(self):
        notifier = Notifier(program=str(self.program))
        clicks = []
        notifier.activated.connect(lambda sid, action: clicks.append((sid, action)))
        os.environ["FAKE_ACTION"] = "retry"
        self.assertTrue(
            notifier.notify("s_1", "lost", "orders-db", "Connection lost", "en", "normal")
        )
        self.assertFalse(notifier.notify("s_1", "lost", "orders-db", "again", "en"), "throttled")
        self.assertTrue(notifier.notify("s_2", "failed", "cache", "Failed", "fa", "critical"))
        self.assertTrue(wait_until(lambda: len(clicks) == 2 and not notifier.pending))
        notifier.shutdown()
        self.assertEqual(clicks[0], ("s_1", "retry"))
        calls = self.log.read_text()
        self.assertIn("--app-name=Bandar", calls)
        self.assertIn(f"--hint=string:desktop-entry:{APP_ID}", calls)
        self.assertIn("--action=retry=Retry", calls)
        self.assertIn("--action=retry=تلاش دوباره", calls)
        self.assertIn("--urgency=critical", calls)

    def test_tray_is_the_fallback(self):
        class Tray:
            messages = []

            def notify(self, title, body, error=False):
                self.messages.append((title, body, error))

        tray = Tray()
        notifier = Notifier(tray=tray, program="")
        notifier.notify("s_1", "failed", "db", "Failed", "en", "critical")
        self.assertEqual(tray.messages, [("db", "Failed", True)])


if __name__ == "__main__":
    unittest.main()
