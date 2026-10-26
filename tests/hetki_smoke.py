#!/usr/bin/env python3
"""Optional real-Hetki smoke test with isolated tmux, HOME, and status service."""
from contextlib import ExitStack
import fcntl
import os
from pathlib import Path
import pty
import shutil
import struct
import subprocess
import termios
import threading

from support import StickyTestCase


def main():
    hetki = shutil.which("hetki")
    if not hetki:
        raise SystemExit("Install hetki before running make smoke-hetki")
    # Register every cleanup immediately. ExitStack runs later cleanups even if
    # one action raises, including timeouts in application/service shutdown.
    with ExitStack() as resources:
        test = StickyTestCase()
        resources.callback(test.doCleanups)
        test.setUp()
        app_env = dict(test.env)
        for key in ("HOME", "XDG_CACHE_HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_RUNTIME_DIR"):
            directory = Path(test.temp.name) / key.lower()
            directory.mkdir(mode=0o700)
            app_env[key] = str(directory)
        master, slave = pty.openpty()
        resources.callback(os.close, master)
        resources.callback(os.close, slave)
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 160, 0, 0))
        client_env = dict(app_env, TERM="xterm-256color")
        client_env.pop("TMUX", None)
        client_env.pop("TMUX_PANE", None)
        client = subprocess.Popen(["tmux", "-S", test.socket, "attach-session", "-t", test.session],
                                  env=client_env, stdin=slave, stdout=slave, stderr=slave)

        def stop_client():
            client.terminate()
            try:
                client.wait(timeout=5)
            except subprocess.TimeoutExpired:
                client.kill()
                client.wait(timeout=5)
        resources.callback(stop_client)
        resources.callback(subprocess.run, [hetki, "service", "stop"], env=app_env, capture_output=True, timeout=10)
        resources.callback(test.cli, "kill", check=False)

        def drain():
            try:
                while os.read(master, 65536):
                    pass
            except OSError:
                pass
        threading.Thread(target=drain, daemon=True).start()
        test.install()
        assignments = [f"{key}={app_env[key]}" for key in app_env if key == "HOME" or key.startswith("XDG_")]
        test.cli("show", "--", "env", *assignments, hetki, "--height", "100%", "--preview")
        first = test.status()
        pane = first["pane"]
        test.assertEqual(first["state"], "visible")
        capture = lambda: test.tmux("capture-pane", "-p", "-t", pane)
        test.eventually(lambda: test.assertIn("project", capture()))
        test.tmux("send-keys", "-t", pane, "-l", "/stickyprobe")
        test.eventually(lambda: test.assertIn("stickyprobe", capture()))
        test.cli("hide")
        test.cli("show")
        test.assertEqual(test.status()["pid"], first["pid"])
        test.eventually(lambda: test.assertIn("stickyprobe", capture()))
        other = test.tmux("new-window", "-t", test.session, "-n", "destination", "-P", "-F", "#{pane_id}", "sleep", "600")
        test.eventually(lambda: test.assertEqual(test.info(pane, "window_id"), test.info(other, "window_id")))
        test.assertEqual(test.status()["pid"], first["pid"])
        test.eventually(lambda: test.assertIn("stickyprobe", capture()))
        print("PASS: Hetki renders at 30% width and preserves PID and search text through hide/show and automatic follow.")
        test.tmux("send-keys", "-t", pane, "C-u")
        test.tmux("send-keys", "-t", pane, "-l", "project")
        test.eventually(lambda: test.assertNotIn("no matching items", capture()))
        test.tmux("send-keys", "-t", pane, "Enter")

        def selected_exits():
            state = test.status()["state"]
            screen = capture() if state != "absent" else ""
            test.assertEqual(state, "absent", screen)
        test.eventually(selected_exits)
        print("CONFIRMED: selecting a destination exits this Hetki version; a persistent navigation mode needs support in Hetki.")


if __name__ == "__main__":
    main()
