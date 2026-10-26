#!/usr/bin/env python3
"""Public CLI/plugin integration tests. Never connects to the user's tmux server."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "tmux-sticky"
PLUGIN = ROOT / "sticky.tmux"


class StickyTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sticky-test-", dir="/tmp")
        self.addCleanup(self.temp.cleanup)
        self.socket = str(Path(self.temp.name) / "socket")
        self.env = {k: v for k, v in os.environ.items() if k not in ("TMUX", "TMUX_PANE")}
        self.tmux("-f", "/dev/null", "new-session", "-d", "-s", "project", "-x", "160", "-y", "50", "sleep", "600")
        self.addCleanup(lambda: self.tmux("kill-server", check=False))
        self.target = self.tmux("display-message", "-p", "-t", "project", "#{pane_id}")
        self.session = self.info(self.target, "session_id")
        self.window = self.info(self.target, "window_id")
        pid = self.tmux("display-message", "-p", "#{pid}")
        self.env.update(TMUX=f"{self.socket},{pid},0", TMUX_PANE=self.target)

    def tmux(self, *args, check=True):
        result = subprocess.run(["tmux", "-S", self.socket, *args], env=self.env, text=True,
                                capture_output=True, timeout=10)
        if check and result.returncode:
            self.fail(f"tmux {args}: {result.stderr}")
        return result.stdout.strip()

    def cli(self, *args, check=True, env=None):
        result = subprocess.run(["sh", str(CLI), *args], env=env or self.env,
                                text=True, capture_output=True, timeout=10)
        if check and result.returncode:
            self.fail(f"tmux-sticky {args}: {result.stderr}")
        return result

    def info(self, target, field):
        return self.tmux("display-message", "-p", "-t", target, "#{" + field + "}")

    def status(self, target=None):
        return dict(line.split("=", 1) for line in self.cli("status", "--target", target or self.target).stdout.splitlines())

    def show(self, *args):
        self.cli("show", *args, "--", "sleep", "600")
        return self.status()

    def eventually(self, assertion):
        deadline = time.monotonic() + 5
        while True:
            try:
                return assertion()
            except AssertionError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.03)

    def binding(self, key):
        lines = self.tmux("list-keys", "-T", "prefix").splitlines()
        return "\n".join(line for line in lines if shlex.split(line)[shlex.split(line).index("-T") + 2] == key)

    def install(self, plugin=PLUGIN):
        result = subprocess.run(["sh", str(plugin)], env=self.env, text=True,
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
