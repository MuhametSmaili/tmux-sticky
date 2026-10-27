"""Regression coverage for lifecycle and concurrency review findings."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import time

from support import CLI, StickyTestCase


class ReviewRegressions(StickyTestCase):
    def wrapper(self, code, **values):
        directory = Path(self.temp.name) / 'review-wrapper'
        directory.mkdir(exist_ok=True)
        script = directory / 'tmux'
        script.write_text('#!/bin/sh\n' + code + '\n')
        script.chmod(0o755)
        env = dict(self.env, PATH=str(directory) + os.pathsep + self.env['PATH'])
        env.update(values)
        return env

    def wait_file(self, path):
        deadline = time.monotonic() + 8
        while not path.exists():
            if time.monotonic() >= deadline:
                self.fail('Barrier not reached: ' + str(path))
            time.sleep(0.01)

    def test_layout_restore_does_not_overwrite_interleaved_resize(self):
        self.tmux('split-window', '-d', '-h', '-t', self.target, 'sleep', '600')
        before = self.info(self.window, 'window_layout')
        self.install()
        self.show()
        directory = Path(self.temp.name)
        ready, release = directory / 'restore-ready', directory / 'restore-release'
        real = shlex.quote(shutil.which('tmux'))
        env = self.wrapper(f'''restore=0
for arg do case "$arg" in *select-layout*) restore=1 ;; esac; done
if [ "$restore" = 1 ] && [ ! -e "$REVIEW_READY" ]; then
    : > "$REVIEW_READY"
    attempts=0
    while [ ! -e "$REVIEW_RELEASE" ]; do
        attempts=$((attempts + 1)); [ "$attempts" -lt 800 ] || exit 88
        sleep 0.01
    done
fi
exec {real} "$@"''', REVIEW_READY=str(ready), REVIEW_RELEASE=str(release))
        process = subprocess.Popen(['sh', str(CLI), 'hide'], env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: release.touch())
        try:
            self.wait_file(ready)
            self.tmux('resize-pane', '-t', self.target, '-R', '7')
            edited = self.info(self.window, 'window_layout')
            self.assertNotEqual(edited, before)
            release.touch()
            stdout, stderr = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, stderr)
            final = self.info(self.window, 'window_layout')
            self.assertEqual(final, edited,
                             f'Intentional edit overwritten; original={before}, edited={edited}, final={final}')
        finally:
            release.touch()
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)


    def test_committed_reopen_failure_recovers_visible_state(self):
        for scope in ("session", "shared"):
            for post in ("exit 1", 'kill -TERM "$PPID"'):
                with self.subTest(scope=scope, failure=post):
                    def status():
                        return dict(line.split("=", 1) for line in
                                    self.cli("status", "--scope", scope).stdout.splitlines())
                    self.cli("show", "--scope", scope, "--", "sleep", "600")
                    opened = status()
                    self.cli("hide", "--scope", scope)
                    self.assertEqual(status()["state"], "parked")
                    real = shlex.quote(shutil.which("tmux"))
                    env = self.wrapper(f'''move=0
for arg do [ "$arg" != join-pane ] || move=1; done
{real} "$@"
result=$?
if [ "$move" = 1 ] && [ "$result" = 0 ]; then {post}; fi
exit "$result"''')
                    result = self.cli("show", "--scope", scope, check=False, env=env)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(self.info(opened["pane"], "window_id"), self.window)
                    flags = ["-sqv"] if scope == "shared" else ["-qv", "-t", self.session]
                    self.assertEqual(self.tmux("show-option", *flags, "@sticky-state-visible"), "1")
                    self.assertEqual(status()["state"], "visible")
                    self.assertEqual(status()["pid"], opened["pid"])
                    self.cli("hide", "--scope", scope)
                    self.assertEqual(status()["state"], "parked")
                    self.cli("kill", "--scope", scope)

    def test_explicit_target_wins_over_inferred_and_explicit_clients(self):
        self.tmux("set-option", "-g", "@sticky-follow-sessions", "on")
        client = self.attach(self.session)
        directory = Path(self.temp.name) / "destination"
        directory.mkdir()
        inactive = self.tmux("new-window", "-d", "-t", self.session, "-c", str(directory),
                             "-P", "-F", "#{pane_id}", "sleep", "600")
        for explicit_client in (False, True):
            with self.subTest(explicit_client=explicit_client):
                options = ["--client", client] if explicit_client else []
                self.cli("show", "--target", inactive, "--scope", "shared", "--focus", "off",
                         *options, "--", "sleep", "600")
                pane = self.tmux("show-option", "-sqv", "@sticky-state-pane")
                self.assertEqual(self.info(pane, "window_id"), self.info(inactive, "window_id"))
                self.assertEqual(Path(self.info(pane, "pane_current_path")).resolve(), directory.resolve())
                self.cli("kill", "--scope", "shared")

    def test_cross_scope_opens_cannot_claim_one_window_twice(self):
        self.cli('show', '--scope', 'shared', '--', 'sleep', '600')
        self.cli('hide', '--scope', 'shared')
        self.cli('show', '--scope', 'session', '--', 'sleep', '600')
        self.cli('hide', '--scope', 'session')
        self.tmux('set-option', '-g', '@sticky-follow-sessions', 'on')
        self.assertEqual(self.info(self.window, 'window_panes'), '1')
        real = shlex.quote(shutil.which('tmux'))
        directory = Path(self.temp.name)
        env = self.wrapper(f'''last=''
for arg do last=$arg; done
if [ "$1" = show-option ] && [ "$last" = @sticky-layout-owner ] && [ ! -e "$REVIEW_BARRIER/$REVIEW_SCOPE" ]; then
    value=$({real} "$@")
    result=$?
    : > "$REVIEW_BARRIER/$REVIEW_SCOPE"
    attempts=0
    while [ ! -e "$REVIEW_BARRIER/session" ] || [ ! -e "$REVIEW_BARRIER/shared" ]; do
        attempts=$((attempts + 1)); [ "$attempts" -lt 800 ] || exit 89
        sleep 0.01
    done
    printf '%s' "$value"
    exit "$result"
fi
exec {real} "$@"''', REVIEW_BARRIER=str(directory))
        processes = []
        try:
            for scope in ('session', 'shared'):
                child = subprocess.Popen(['sh', str(CLI), 'show', '--scope', scope],
                                         env=dict(env, REVIEW_SCOPE=scope),
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                processes.append(child)
            results = [p.communicate(timeout=15) for p in processes]
            panes = self.tmux('list-panes', '-t', self.window,
                              '-F', '#{pane_id}:#{@sticky-owner}').splitlines()
            self.assertEqual(len(panes), 2,
                             f'Both independent scopes inserted a sidebar into one window: {panes}')
            self.assertEqual(sorted(p.returncode for p in processes), [0, 1], results)
            self.assertIn("another sidebar", "".join(err for out, err in results))
            winner = ("session", "shared")[next(i for i, p in enumerate(processes) if p.returncode == 0)]
            loser = "shared" if winner == "session" else "session"
            self.cli("kill", "--scope", winner)
            self.cli("show", "--scope", loser)
            self.assertEqual(self.info(self.window, "window_panes"), "2")
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
