#!/usr/bin/env python3
"""Public CLI/plugin integration tests. Never connects to the user's tmux server."""
from contextlib import ExitStack
import fcntl
import json
import os
from pathlib import Path
import pty
import shlex
import struct
import subprocess
import termios
import threading
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
        value = self.tmux("display-message", "-p", "-t", target, "#{" + field + "}")
        if field == "window_layout" and value.startswith("{"):
            # Geometry comparisons must not include 3.8 focus/history/indexes.
            def geometry(node):
                return {key: [geometry(child) for child in item] if key == "c" else item
                        for key, item in node.items() if key not in ("a", "l", "i")}
            data = json.loads(value)
            data["L"] = geometry(data["L"])
            return json.dumps(data, separators=(",", ":"), sort_keys=True)
        return value

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

    def attach(self, session, *, control=False):
        resources = ExitStack()
        self.addCleanup(resources.close)
        env = dict(self.env, TERM="xterm-256color")
        env.pop("TMUX", None)
        env.pop("TMUX_PANE", None)
        if control:
            process = subprocess.Popen(["tmux", "-S", self.socket, "-C", "attach-session", "-t", session],
                                       env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            for stream in (process.stdin, process.stdout, process.stderr):
                resources.callback(stream.close)
        else:
            master, slave = pty.openpty()
            resources.callback(os.close, master)
            resources.callback(os.close, slave)
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 160, 0, 0))
            process = subprocess.Popen(["tmux", "-S", self.socket, "attach-session", "-t", session],
                                       env=env, stdin=slave, stdout=slave, stderr=slave)
            def drain():
                try:
                    while os.read(master, 65536):
                        pass
                except OSError:
                    pass
            threading.Thread(target=drain, daemon=True).start()
        def close():
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        resources.callback(close)
        found = []
        def registered():
            for line in self.tmux("list-clients", "-F", "#{client_pid} #{client_name}").splitlines():
                pid, name = line.split(" ", 1)
                if pid == str(process.pid):
                    found.append(name)
                    return
            self.fail("Client has not attached yet")
        self.eventually(registered)
        return found[-1]

    def binding(self, key):
        lines = self.tmux("list-keys", "-T", "prefix").splitlines()
        return "\n".join(line for line in lines if shlex.split(line)[shlex.split(line).index("-T") + 2] == key)

    def install(self, plugin=PLUGIN):
        result = subprocess.run(["sh", str(plugin)], env=self.env, text=True,
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

