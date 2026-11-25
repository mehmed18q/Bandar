"""Start a frozen bundle for real and check that it serves its window, then quits cleanly.

python tests/bundle_smoke.py build/onedir/Bandar/Bandar
"""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def main():
    executable = Path(sys.argv[1]).resolve()
    version = subprocess.check_output([str(executable), "--version"], text=True).strip()
    assert version.startswith("Bandar "), version
    with tempfile.TemporaryDirectory() as home:
        config = Path(home) / "config.json"
        env = {**os.environ, "HOME": home, "XDG_CONFIG_HOME": home, "XDG_DATA_HOME": home}
        process = subprocess.Popen([str(executable), "--config", str(config)], env=env)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline and not config.exists() and process.poll() is None:
            time.sleep(0.5)
        time.sleep(3)
        alive = process.poll() is None
        process.terminate()
        code = process.wait(20)
        log = Path(home) / "logs" / "bandar.log"
        print(log.read_text() if log.exists() else "(no log)")
        assert alive, "the bundle exited during startup"
        assert code == 0, f"exit code {code}"
        assert config.exists(), "the configuration was never written"
    print(f"Bundle OK: {version}")


if __name__ == "__main__":
    main()
