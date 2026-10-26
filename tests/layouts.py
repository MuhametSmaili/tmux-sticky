"""Layout preservation through the public CLI on isolated tmux servers."""
import os
import signal

from support import StickyTestCase


class StickyLayouts(StickyTestCase):
    def split(self, target=None):
        return self.tmux("split-window", "-d", "-h", "-t", target or self.target,
                         "-P", "-F", "#{pane_id}", "sleep", "600")

    def layout(self, target=None):
        return self.info(target or self.target, "window_layout")

    def test_left_sidebar_restores_an_unequal_nested_layout(self):
        other = self.split()
        self.tmux("resize-pane", "-t", other, "-x", "55")
        self.tmux("split-window", "-d", "-v", "-t", other, "sleep", "600")
        before = self.layout()
        for _ in range(3):
            self.show("--side", "left")
            self.cli("hide")
            self.assertEqual(self.layout(), before)

    def test_follow_restores_each_window_independently(self):
        self.split()
        original = self.layout()
        other = self.tmux("new-window", "-t", self.session, "-P", "-F", "#{pane_id}", "sleep", "600")
        self.split(other)
        self.tmux("resize-pane", "-t", other, "-x", "65")
        other_layout = self.layout(other)
        self.tmux("select-window", "-t", self.window)
        opened = self.show()
        for _ in range(2):
            self.tmux("select-window", "-t", self.info(other, "window_id"))
            self.cli("follow", self.session)
            self.assertEqual(self.layout(), original)
            self.tmux("select-window", "-t", self.window)
            self.cli("follow", self.session)
            self.assertEqual(self.layout(other), other_layout)
        self.cli("hide")
        self.assertEqual(self.layout(), original)
        self.assertEqual(self.status()["pid"], opened["pid"])

    def test_vertical_content_with_nested_columns_restores_exactly(self):
        bottom = self.tmux("split-window", "-d", "-v", "-t", self.target, "-P", "-F", "#{pane_id}", "sleep", "600")
        self.split(bottom)
        before = self.layout()
        for side in ("left", "right"):
            self.show("--side", side)
            self.cli("hide")
            self.assertEqual(self.layout(), before)

    def test_manual_resize_is_not_replaced_with_an_old_snapshot(self):
        self.split()
        before = self.layout()
        self.show()
        self.tmux("resize-pane", "-t", self.target, "-x", "40")
        self.cli("hide")
        self.assertEqual(self.info(self.target, "pane_width"), "40")
        self.assertNotEqual(self.layout(), before)
        edited = self.layout()
        self.cli("show")
        self.cli("hide")
        self.assertEqual(self.layout(), edited)

    def test_added_main_pane_is_not_removed_or_rearranged(self):
        self.split()
        self.show()
        added = self.tmux("split-window", "-d", "-v", "-t", self.target, "-P", "-F", "#{pane_id}", "sleep", "600")
        height = self.info(added, "pane_height")
        self.cli("hide")
        self.assertEqual(self.info(self.target, "window_panes"), "3")
        self.assertEqual(self.info(added, "pane_height"), height)
        edited = self.layout()
        self.cli("show")
        self.cli("hide")
        self.assertEqual(self.layout(), edited)

    def test_resize_next_to_sidebar_invalidates_snapshot_before_hide(self):
        other = self.split()
        before = self.layout()
        self.show()
        self.tmux("resize-pane", "-t", other, "-x", "40")
        self.cli("hide")
        self.assertNotEqual(self.layout(), before)

    def test_application_exit_after_adjacent_resize_keeps_the_edit(self):
        other = self.split()
        before = self.layout()
        self.install()
        opened = self.show()
        self.tmux("resize-pane", "-t", other, "-x", "40")
        os.kill(int(opened["pid"]), signal.SIGTERM)
        self.eventually(lambda: self.assertEqual(self.info(self.target, "window_panes"), "2"))
        self.cli("cleanup")
        self.assertNotEqual(self.layout(), before)

    def test_window_resize_invalidates_the_old_snapshot(self):
        self.split()
        self.show()
        self.tmux("resize-window", "-t", self.window, "-x", "200", "-y", "60")
        width = self.info(self.target, "pane_width")
        self.cli("hide")
        self.assertEqual(self.info(self.target, "window_width"), "200")
        self.assertEqual(self.info(self.target, "pane_width"), width)

    def test_explicit_kill_restores_the_main_layout(self):
        self.split()
        before = self.layout()
        self.show()
        self.cli("kill")
        self.assertEqual(self.layout(), before)

    def test_application_exit_restores_without_a_status_query(self):
        self.split()
        before = self.layout()
        self.install()
        opened = self.show()
        os.kill(int(opened["pid"]), signal.SIGTERM)
        self.eventually(lambda: self.assertEqual(self.layout(), before))

    def test_manual_sidebar_pane_close_restores_the_main_layout(self):
        self.split()
        before = self.layout()
        self.install()
        opened = self.show()
        self.tmux("kill-pane", "-t", opened["pane"])
        self.eventually(lambda: self.assertEqual(self.layout(), before))

    def test_removing_a_main_pane_does_not_replay_old_topology(self):
        other = self.split()
        self.show()
        self.tmux("kill-pane", "-t", other)
        self.cli("hide")
        self.assertEqual(self.info(self.target, "window_panes"), "1")
        self.assertEqual(self.info(self.target, "pane_width"), "160")

    def test_repeated_right_sidebar_toggles_restore_a_half_split(self):
        self.tmux("resize-window", "-t", self.window, "-x", "164", "-y", "41")
        other = self.split()
        before = self.layout()
        original_widths = (self.info(self.target, "pane_width"), self.info(other, "pane_width"))
        pid = None
        for _ in range(3):
            state = self.show()
            pid = pid or state["pid"]
            self.assertEqual(state["pid"], pid)
            self.assertEqual(self.info(state["pane"], "pane_width"), "49")
            self.assertLessEqual(abs(int(self.info(self.target, "pane_width")) - int(self.info(other, "pane_width"))), 1)
            self.cli("hide")
            self.assertEqual(self.layout(), before)
            self.assertEqual((self.info(self.target, "pane_width"), self.info(other, "pane_width")), original_widths)
