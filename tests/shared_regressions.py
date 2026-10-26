"""Shared ownership migration and lifecycle failure regressions."""
from pathlib import Path
import shlex
import shutil

from support import StickyTestCase


class SharedRegressions(StickyTestCase):
    def test_replacing_a_stale_shared_pane_keeps_automatic_following(self):
        self.tmux("set-option", "-g", "@sticky-follow-sessions", "on")
        human = self.attach(self.session)
        self.cli("show", "--client", human, "--", "sleep", "600")
        old = next(p for p in self.tmux("list-panes", "-t", self.window, "-F", "#{pane_id}").splitlines() if p != self.target)
        self.tmux("kill-pane", "-t", old)  # No plugin hooks loaded: leave stale state.
        self.cli("show", "--client", human, "--", "sleep", "600")
        new = next(p for p in self.tmux("list-panes", "-t", self.window, "-F", "#{pane_id}").splitlines() if p != self.target)
        self.install()
        other = self.tmux("new-session", "-d", "-s", "second", "-P", "-F", "#{pane_id}", "sleep", "600")
        self.tmux("switch-client", "-c", human, "-t", self.info(other, "session_id"))
        self.eventually(lambda: self.assertEqual(self.info(new, "window_id"), self.info(other, "window_id")))

    def test_stale_shared_state_does_not_block_local_pane_adoption(self):
        self.tmux("set-option", "-g", "@sticky-follow-sessions", "on")
        global_app = self.show()
        other = self.tmux("new-session", "-d", "-s", "second", "-P", "-F", "#{pane_id}", "sleep", "600")
        self.tmux("kill-pane", "-t", global_app["pane"])
        self.cli("show", "--scope", "session", "--target", other, "--", "sleep", "600")
        local_pane = next(p for p in self.tmux("list-panes", "-t", other, "-F", "#{pane_id}").splitlines() if p != other)
        pid = self.info(local_pane, "pane_pid")
        self.cli("show", "--target", other)
        self.assertEqual(self.status(other)["pid"], pid)
        self.assertEqual(self.status(other)["pane"], local_pane)

    def test_hide_does_not_transfer_control_even_when_already_hidden(self):
        self.tmux("set-option", "-g", "@sticky-follow-sessions", "on")
        first = self.attach(self.session)
        self.cli("show", "--client", first, "--", "sleep", "600")
        self.cli("hide")
        other = self.tmux("new-session", "-d", "-s", "second", "-P", "-F", "#{pane_id}", "sleep", "600")
        second = self.attach(self.info(other, "session_id"))
        self.cli("hide", "--target", other, "--client", second)
        self.assertEqual(self.status(other)["client"], first)

    def test_interrupted_adoption_keeps_the_app_and_releases_both_locks(self):
        opened = self.show()
        self.cli("hide")
        self.tmux("set-option", "-g", "@sticky-follow-sessions", "on")
        directory = Path(self.temp.name) / "wrapper"
        directory.mkdir()
        wrapper = directory / "tmux"
        real = shlex.quote(shutil.which("tmux"))
        wrapper.write_text(f'''#!/bin/sh
owner=0; shared=0
for arg in "$@"; do
    [ "$arg" != @sticky-owner ] || owner=1
    [ "$arg" != shared ] || shared=1
done
{real} "$@"
result=$?
if [ "$owner:$shared" = 1:1 ]; then kill -TERM "$PPID"; fi
exit "$result"
''')
        wrapper.chmod(0o755)
        env = dict(self.env, PATH=str(directory) + ":" + self.env["PATH"])
        result = self.cli("status", check=False, env=env)
        self.assertNotEqual(result.returncode, 0)
        adopted = self.status()
        self.assertEqual(adopted["state"], "parked")
        self.assertEqual(adopted["pid"], opened["pid"])
        self.cli("show")
        self.assertEqual(self.status()["pid"], opened["pid"])
        local = self.cli("status", "--scope", "session").stdout
        self.assertIn("state=absent", local)

    def test_adoption_does_not_overwrite_an_unowned_parking_name(self):
        opened = self.show()
        self.cli("hide")
        other = self.tmux("new-session", "-d", "-s", "__tmux_sticky_shared", "-P", "-F", "#{pane_id}", "sleep", "600")
        self.tmux("set-option", "-g", "@sticky-follow-sessions", "on")
        self.assertNotEqual(self.cli("status", check=False).returncode, 0)
        self.assertEqual(self.info(opened["pane"], "pane_pid"), opened["pid"])
        self.assertEqual(self.info(other, "pane_dead"), "0")
        self.tmux("kill-session", "-t", self.info(other, "session_id"))
        self.assertEqual(self.status()["pid"], opened["pid"])

    def test_closing_the_original_project_does_not_end_a_moved_shared_app(self):
        self.tmux("set-option", "-g", "@sticky-follow-sessions", "on")
        opened = self.show()
        other = self.tmux("new-session", "-d", "-s", "second", "-P", "-F", "#{pane_id}", "sleep", "600")
        self.cli("show", "--target", other)
        self.tmux("kill-session", "-t", self.session)
        self.cli("cleanup")
        state = self.status(other)
        self.assertEqual((state["pane"], state["pid"]), (opened["pane"], opened["pid"]))
        self.assertEqual(state["state"], "visible")
