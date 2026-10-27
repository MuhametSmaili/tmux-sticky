# Ignore tmux 3.8 focus/history metadata; retain required pane indexes.
layout_format='#{s/,"[al]"#:(true|[0-9]+)//:window_layout}'
# Control clients can still expose V1 while ordinary clients expose V2.
layout_signature='#{window_width}x#{window_height}:#{P:#{pane_id}/#{pane_width}/#{pane_height}/#{pane_left}/#{pane_top};}'
# A nested tmux command must retain JSON quotes through both parse layers.
layout_quote() {
    printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"
}
