#!/usr/bin/env python3
"""Public behavior tests against isolated tmux servers."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import fcntl
import os
from pathlib import Path
import pty
import shlex
import shutil
import signal
import struct
import subprocess
import termios
import threading
import unittest

from support import PLUGIN, ROOT, StickyTestCase


class StickyIntegration(StickyTestCase):
    def test_toggle_parks_and_restores_the_same_process(self):
        opened = self.show()
        self.cli("toggle", "--target", opened["pane"])
        hidden = self.status()
        self.assertEqual(hidden["state"], "parked")
        self.assertEqual((hidden["pane"], hidden["pid"]), (opened["pane"], opened["pid"]))
        self.assertNotEqual(self.info(hidden["pane"], "session_id"), self.session)
        self.assertEqual(self.info(hidden["pane"], "window_panes"), "1")
        self.assertEqual(self.info(self.target, "window_panes"), "1")
        self.cli("hide")  # Idempotent.
        self.cli("toggle")
        self.assertEqual(self.status(), opened)
        self.assertEqual(self.tmux("list-sessions", "-F", "#{session_id}"), self.session)
        self.cli("kill")
        self.cli("kill")
        self.assertEqual(self.status()["state"], "absent")
        self.assertEqual(self.info(self.target, "window_panes"), "1")

    def test_hiding_last_pane_does_not_destroy_its_owner_session(self):
        opened = self.show()
        self.tmux("kill-pane", "-t", self.target)
        result = self.cli("hide", "--target", opened["pane"], check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("only pane", result.stderr)
        self.assertEqual(self.status(opened["pane"])["state"], "visible")
        self.assertEqual(self.info(opened["pane"], "session_id"), self.session)

    def test_follow_moves_visible_sidebar_without_stealing_focus(self):
        opened = self.show()
        other = self.tmux("new-window", "-t", self.session, "-P", "-F", "#{pane_id}", "sleep", "600")
        self.cli("follow", self.session)
        self.assertEqual(self.info(opened["pane"], "window_id"), self.info(other, "window_id"))
        self.assertEqual(self.info(other, "pane_active"), "1")
        self.assertEqual(self.status()["pid"], opened["pid"])
        self.cli("hide", "--target", other)
        parked_window = self.info(opened["pane"], "window_id")
        self.tmux("select-window", "-t", self.window)
        self.cli("follow", self.session)
        self.assertEqual(self.info(opened["pane"], "window_id"), parked_window)

    def test_cleanup_removes_orphan_parking_and_recovers_closed_app(self):
        opened = self.show()
        self.tmux("kill-pane", "-t", opened["pane"])
        self.cli("cleanup")
        self.assertEqual(self.status()["state"], "absent")
        self.show()
        self.cli("hide")
        self.tmux("new-session", "-d", "-s", "survivor", "sleep", "600")
        self.tmux("kill-session", "-t", self.session)
        self.cli("cleanup")
        self.assertEqual(self.tmux("list-sessions", "-F", "#{session_name}"), "survivor")

    def test_plugin_reload_preserves_process_and_unrelated_hooks(self):
        self.tmux("set-hook", "-g", "session-window-changed[30000]", "set-option -g @other-hook ran")
        self.install()
        opened = self.show()
        self.install()
        hooks = self.tmux("show-hooks", "-g", "session-window-changed")
        self.assertIn("@other-hook", hooks)
        self.assertEqual(hooks.count("tmux-sticky/session-window-changed"), 1)
        self.assertEqual(self.status(), opened)
        other = self.tmux("new-window", "-t", self.session, "-P", "-F", "#{pane_id}", "sleep", "600")
        self.eventually(lambda: self.assertEqual(self.info(opened["pane"], "window_id"), self.info(other, "window_id")))
        self.assertEqual(self.info(other, "pane_active"), "1")
        self.assertEqual(self.tmux("show-option", "-gqv", "@other-hook"), "ran")
        self.cli("hide", "--target", other)
        self.tmux("new-session", "-d", "-s", "survivor", "sleep", "600")
        self.tmux("kill-session", "-t", self.session)
        self.eventually(lambda: self.assertEqual(self.tmux("list-sessions", "-F", "#{session_name}"), "survivor"))

    def test_zoomed_and_too_narrow_windows_fail_without_changing_layout(self):
        self.tmux("split-window", "-d", "-t", self.target, "sleep", "600")
        self.tmux("resize-pane", "-Z", "-t", self.target)
        result = self.cli("show", "--", "sleep", "600", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("zoom", result.stderr.lower())
        self.assertEqual(self.info(self.target, "window_zoomed_flag"), "1")
        self.assertEqual(self.info(self.target, "window_panes"), "2")
        self.tmux("resize-pane", "-Z", "-t", self.target)
        self.tmux("resize-window", "-t", self.window, "-x", "20", "-y", "10")
        result = self.cli("show", "--width", "15", "--", "sleep", "600", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("narrow", result.stderr.lower())
        self.assertEqual(self.status()["state"], "absent")

    def test_configuration_controls_side_size_focus_and_session_override(self):
        self.tmux("set-option", "-g", "@sticky-command", "exec sleep 600")
        self.tmux("set-option", "-g", "@sticky-width", "30%")
        self.tmux("set-option", "-t", self.session, "@sticky-width", "40")
        self.tmux("set-option", "-g", "@sticky-side", "left")
        self.tmux("set-option", "-g", "@sticky-focus", "off")
        self.cli("toggle")
        state = self.status()
        self.assertEqual(self.info(state["pane"], "pane_width"), "40")
        self.assertEqual(self.info(state["pane"], "pane_left"), "0")
        self.assertEqual(self.info(self.target, "pane_active"), "1")
        self.cli("hide")
        self.cli("show", "--side", "right", "--width", "25%", "--focus", "on")
        self.assertEqual(self.info(state["pane"], "pane_width"), "40")
        self.assertEqual(self.info(state["pane"], "pane_active"), "1")
        self.assertEqual(self.status()["pid"], state["pid"])

    def test_command_arguments_and_initial_directory_are_preserved(self):
        directory = Path(self.temp.name) / "project's files"
        directory.mkdir()
        output = directory / "result.txt"
        target = self.tmux("new-window", "-t", self.session, "-c", str(directory), "-P", "-F", "#{pane_id}", "sleep", "600")
        arguments = ["a b", "a'b", 'a"b', "$HOME; echo not-executed", "#literal"]
        self.cli("show", "--target", target, "--", "/bin/sh", "-c",
                 'printf "%s\\n" "$PWD" "$@" > "$1"; exec sleep 600', "sidebar", str(output), *arguments)
        expected = [str(directory.resolve()), str(output), *arguments]
        self.eventually(lambda: self.assertEqual(output.read_text().splitlines() if output.exists() else None, expected))
        self.assertEqual(self.info(self.status(target)["pane"], "pane_current_path"), str(directory.resolve()))

    def test_configured_command_is_one_trusted_shell_string(self):
        output = Path(self.temp.name) / "configured output"
        self.tmux("set-option", "-g", "@sticky-command", f"printf ready > {shlex.quote(str(output))}; exec sleep 600")
        self.cli("show")
        self.eventually(lambda: self.assertEqual(output.read_text() if output.exists() else None, "ready"))

    def test_missing_command_and_invalid_options_do_not_create_panes(self):
        self.assertNotEqual(self.cli("show", check=False).returncode, 0)
        for args in [("--side", "top"), ("--width", "0"), ("--width", "08"),
                     ("--width", "101%"), ("--width", "-5"), ("--focus", "maybe"),
                     ("--target", "%999999"), ("--width",)]:
            with self.subTest(args=args):
                self.assertNotEqual(self.cli("show", *args, check=False).returncode, 0)
        self.assertEqual(self.info(self.target, "window_panes"), "1")
        self.assertEqual(self.status()["state"], "absent")
        self.assertEqual(self.cli("--help").returncode, 0)

    def test_sessions_keep_independent_sidebars(self):
        first = self.show()
        other = self.tmux("new-session", "-d", "-s", "another-project", "-P", "-F", "#{pane_id}", "sleep", "600")
        self.cli("show", "--target", other, "--", "sleep", "600")
        second = self.status(other)
        self.assertNotEqual(second["pane"], first["pane"])
        self.assertEqual(self.info(first["pane"], "session_id"), self.session)
        self.cli("hide", "--target", other)
        self.assertEqual(self.status(), first)
        self.tmux("rename-session", "-t", self.session, "renamed")
        self.assertEqual(self.status(), first)

    def test_grouped_sessions_are_rejected(self):
        self.tmux("new-session", "-d", "-s", "group-peer", "-t", self.session)
        result = self.cli("show", "--", "sleep", "600", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Grouped", result.stderr)
        self.assertEqual(self.info(self.target, "window_panes"), "1")

    def test_linked_windows_are_rejected(self):
        self.tmux("new-session", "-d", "-s", "other", "sleep", "600")
        self.tmux("link-window", "-s", self.window, "-t", "other:5")
        result = self.cli("show", "--", "sleep", "600", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Linked", result.stderr)
        self.assertEqual(self.info(self.target, "window_panes"), "1")

    def test_parking_name_collision_does_not_touch_an_unowned_session(self):
        opened = self.show()
        name = "__tmux_sticky_" + self.session.removeprefix("$")
        other = self.tmux("new-session", "-d", "-s", name, "-P", "-F", "#{pane_id}", "sleep", "600")
        self.assertNotEqual(self.cli("hide", check=False).returncode, 0)
        self.assertEqual(self.status(), opened)
        self.cli("cleanup")
        self.assertEqual(self.info(other, "pane_dead"), "0")

    def test_remain_on_exit_panes_are_reaped_and_can_restart(self):
        opened = self.show()
        self.tmux("set-option", "-p", "-t", opened["pane"], "remain-on-exit", "on")
        os.kill(int(opened["pid"]), signal.SIGTERM)
        self.eventually(lambda: self.assertEqual(self.status()["state"], "absent"))
        restarted = self.show()
        self.assertNotEqual(restarted["pane"], opened["pane"])

    def test_concurrent_show_and_toggles_keep_one_process(self):
        def show(_):
            self.cli("show", "--", "sleep", "600")
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(show, range(6)))
        opened = self.status()
        self.assertEqual(self.info(self.target, "window_panes"), "2")
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(lambda _: self.cli("toggle"), range(6)))
        self.assertEqual(self.status(), opened)
        self.assertEqual(self.tmux("list-sessions", "-F", "#{session_id}"), self.session)

    def test_binding_changes_remove_only_owned_bindings(self):
        self.install()
        self.tmux("set-option", "-g", "@sticky-key", "J")
        self.install()
        self.assertEqual(self.binding("H"), "")
        self.assertIn("tmux-sticky/toggle", self.binding("J"))
        self.tmux("bind-key", "J", "display-message", "user-owned")
        self.tmux("set-option", "-g", "@sticky-key", "K")
        self.install()
        self.assertIn("user-owned", self.binding("J"))
        self.assertIn("tmux-sticky/toggle", self.binding("K"))

    def test_install_refuses_to_overwrite_an_unrelated_key(self):
        self.tmux("bind-key", "H", "display-message", "user-owned")
        result = subprocess.run(["sh", str(PLUGIN)], env=self.env, text=True, capture_output=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already bound", result.stderr)
        self.assertIn("user-owned", self.binding("H"))

    def test_key_alias_collision_is_also_preserved(self):
        self.tmux("bind-key", "M-C-a", "display-message", "user-owned-alias")
        self.tmux("set-option", "-g", "@sticky-key", "C-M-a")
        result = subprocess.run(["sh", str(PLUGIN)], env=self.env, text=True, capture_output=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("user-owned-alias", self.tmux("list-keys"))

    def test_installation_path_with_quotes_spaces_and_hash_works(self):
        directory = Path(self.temp.name) / "sticky's # files $"
        shutil.copytree(ROOT, directory, ignore=shutil.ignore_patterns(".git", ".agent", "__pycache__"))
        self.install(directory / "sticky.tmux")
        opened = self.show()
        other = self.tmux("new-window", "-t", self.session, "-P", "-F", "#{pane_id}", "sleep", "600")
        self.eventually(lambda: self.assertEqual(self.info(opened["pane"], "window_id"), self.info(other, "window_id")))

    def test_real_prefix_binding_toggles_and_reports_errors_in_tmux(self):
        resources = ExitStack()
        self.addCleanup(resources.close)
        master, slave = pty.openpty()
        resources.callback(os.close, master)
        resources.callback(os.close, slave)
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 160, 0, 0))
        env = dict(self.env, TERM="xterm-256color")
        env.pop("TMUX", None)
        env.pop("TMUX_PANE", None)
        client = subprocess.Popen(["tmux", "-S", self.socket, "attach-session", "-t", self.session],
                                  env=env, stdin=slave, stdout=slave, stderr=slave)
        def close_client():
            client.terminate()
            try:
                client.wait(timeout=5)
            except subprocess.TimeoutExpired:
                client.kill()
                client.wait(timeout=5)
        resources.callback(close_client)
        def drain():
            try:
                while os.read(master, 65536):
                    pass
            except OSError:
                pass
        threading.Thread(target=drain, daemon=True).start()
        self.tmux("set-option", "-g", "@sticky-command", "exec sleep 600")
        self.install()
        self.eventually(lambda: self.assertEqual(self.info(self.target, "session_attached"), "1"))
        os.write(master, b"\x02H")
        self.eventually(lambda: self.assertEqual(self.status()["state"], "visible"))
        opened = self.status()
        os.write(master, b"\x02H")
        self.eventually(lambda: self.assertEqual(self.status()["state"], "parked"))
        self.assertEqual(self.status()["pid"], opened["pid"])
        self.cli("kill")
        self.tmux("set-option", "-g", "@sticky-command", "")
        os.write(master, b"\x02H")
        self.eventually(lambda: self.assertIn("Set @sticky-command", self.tmux("show-messages")))
        self.assertEqual(self.status()["state"], "absent")

    def test_show_creates_one_sidebar_and_reports_it(self):
        self.assertEqual(self.status()["state"], "absent")
        state = self.show()
        self.assertEqual(state["state"], "visible")
        self.assertEqual(state["session"], self.session)
        self.assertNotEqual(state["pane"], self.target)
        self.assertEqual(self.info(state["pane"], "window_id"), self.window)
        self.assertEqual(self.info(self.target, "window_panes"), "2")
        self.assertGreater(int(state["pid"]), 0)
        self.cli("show")
        self.assertEqual(self.status()["pane"], state["pane"])
        self.assertEqual(self.info(self.target, "window_panes"), "2")


if __name__ == "__main__":
    if not shutil.which("tmux"):
        raise SystemExit("tmux is required")
    unittest.main(verbosity=2)
