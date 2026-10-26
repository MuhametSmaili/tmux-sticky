"""Regression tests for protocol boundaries and interrupted lifecycle operations."""
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import unittest

from support import CLI, PLUGIN, StickyTestCase


class StickyRegressions(StickyTestCase):
    def test_semicolon_key_is_supported_and_can_be_changed(self):
        self.tmux("unbind-key", r"\;")
        self.tmux("set-option", "-g", "@sticky-key", r"\;")
        # Set the literal value separately: the tmux client consumes its escape.
        self.install()
        self.assertIn("tmux-sticky/toggle", self.tmux("list-keys"))
        self.tmux("set-option", "-g", "@sticky-key", "H")
        self.install()
        self.assertEqual(self.tmux("list-keys").count("tmux-sticky/toggle"), 1)

    def test_interrupted_or_failed_open_does_not_leave_an_untracked_app(self):
        real = shlex.quote(shutil.which("tmux"))
        directory = Path(self.temp.name) / "open-wrapper"
        directory.mkdir()
        wrapper = directory / "tmux"
        self.tmux("set-hook", "-g", "after-split-window", f"select-pane -t {self.target}")
        for post in ['kill -TERM "$PPID"', 'exit 1']:
            with self.subTest(post=post):
                wrapper.write_text(f'''#!/bin/sh
{real} "$@"
result=$?
if [ "$1" = split-window ]; then
    {post}
fi
exit "$result"
''')
                wrapper.chmod(0o755)
                env = dict(self.env, PATH=str(directory) + os.pathsep + self.env["PATH"])
                result = self.cli("show", "--focus", "off", "--", "sleep", "600", env=env, check=False)
                self.assertNotEqual(result.returncode, 0)
                opened = self.status()
                self.assertEqual(opened["state"], "visible")
                self.assertEqual(self.info(self.target, "window_panes"), "2")
                self.assertEqual(self.info(self.target, "pane_active"), "1")
                self.cli("show")
                self.assertEqual(self.status(), opened)
                self.cli("kill")

    def test_equivalent_key_change_keeps_the_binding(self):
        self.tmux("set-option", "-g", "@sticky-key", "C-M-a")
        self.install()
        self.tmux("set-option", "-g", "@sticky-key", "M-C-a")
        self.install()
        self.assertIn("tmux-sticky/toggle", self.tmux("list-keys"))

    def test_semicolons_are_arguments_not_tmux_commands(self):
        victim = self.tmux("new-session", "-d", "-s", "victim", "-P", "-F", "#{session_id}", "sleep", "600")
        output = Path(self.temp.name) / "argv"
        args = ["ordinary;", r"escaped\;", ";", "kill-session", "-t", victim]
        self.cli("show", "--", "/bin/sh", "-c", 'printf "%s\\n" "$@" > "$1"; exec sleep 600', "sidebar", str(output), *args)
        expected = [str(output), *args]
        self.eventually(lambda: self.assertEqual(output.read_text().splitlines() if output.exists() else None, expected))
        self.assertIn(victim, self.tmux("list-sessions", "-F", "#{session_id}"))

    def interrupting_env(self, *, close_owner=False, after_move=False):
        real = shlex.quote(shutil.which("tmux"))
        directory = Path(self.temp.name) / "wrapper"
        directory.mkdir()
        wrapper = directory / "tmux"
        post = f"{real} kill-session -t {shlex.quote(self.session)}" if close_owner else 'kill -TERM "$PPID"'
        detect = '[ "$1" != join-pane ] || interrupt=1' if after_move else '''for arg in "$@"; do
    [ "$arg" != @sticky-parking-owner ] || interrupt=1
done'''
        if after_move:
            post = 'exit 1'
        wrapper.write_text(f'''#!/bin/sh
interrupt=0
{detect}
{real} "$@"
result=$?
if [ "$interrupt" = 1 ]; then
    {post}
fi
exit "$result"
''')
        wrapper.chmod(0o755)
        return dict(self.env, PATH=str(directory) + os.pathsep + self.env["PATH"])

    def test_interrupted_hide_recovers_and_can_hide_again(self):
        opened = self.show()
        result = self.cli("hide", check=False, env=self.interrupting_env())
        self.assertNotEqual(result.returncode, 0)
        # Inspect raw tmux first: status must not be needed to clean up the helper.
        self.assertEqual(self.tmux("list-sessions", "-F", "#{session_id}"), self.session)
        self.assertEqual(self.status(), opened)
        self.cli("hide")
        self.assertEqual(self.status()["state"], "parked")

    def test_error_after_committed_move_does_not_kill_the_application(self):
        opened = self.show()
        result = self.cli("hide", check=False, env=self.interrupting_env(after_move=True))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.status()["state"], "parked")
        self.assertEqual(self.status()["pid"], opened["pid"])
        self.assertEqual(self.info(opened["pane"], "window_panes"), "1")
        self.cli("show")
        self.assertEqual(self.status(), opened)

    def test_owner_exit_during_hide_leaves_no_parking_placeholder(self):
        self.show()
        survivor = self.tmux("new-session", "-d", "-s", "survivor", "-P", "-F", "#{session_id}", "sleep", "600")
        self.cli("hide", check=False, env=self.interrupting_env(close_owner=True))
        self.cli("cleanup")
        self.assertEqual(self.tmux("list-sessions", "-F", "#{session_id}"), survivor)

    def test_direct_executable_entrypoints_and_automatic_dead_pane_cleanup(self):
        result = subprocess.run([str(CLI), "--help"], env=self.env, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([str(PLUGIN)], env=self.env, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        opened = self.show()
        self.tmux("set-option", "-p", "-t", opened["pane"], "remain-on-exit", "on")
        os.kill(int(opened["pid"]), signal.SIGTERM)
        self.eventually(lambda: self.assertNotIn(opened["pane"], self.tmux("list-panes", "-a", "-F", "#{pane_id}").splitlines()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
