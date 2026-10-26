# Adopt an existing local instance only when the shared slot is empty.
# Lock order is shared -> session. Session-only commands never take the shared lock.
shared_adopt() {
    [ "$scope" = shared ] && [ "$mode" = on ] && [ -n "$session" ] || return 0
    case "$action" in show|toggle|status) : ;; *) return 0 ;; esac
    [ -z "$(get @sticky-state-pane)" ] || return 0
    sa_pane=$(tmux show-option -qv -t "$session" @sticky-state-pane)
    [ -n "$sa_pane" ] || return 0
    sh "$ROOT/bin/tmux-sticky" _reconcile "$session"
    sa_lock="tmux-sticky-${session#\$}"
    tmux wait-for -L "$sa_lock"
    borrowed_lock=$sa_lock
    sa_pane=$(tmux show-option -qv -t "$session" @sticky-state-pane)
    sa_owner=$(tmux show-option -pqv -t "$sa_pane" @sticky-owner 2>/dev/null || :)
    if [ -z "$sa_pane" ] || [ "$sa_owner" != "$session" ]; then
        tmux wait-for -U "$borrowed_lock"; borrowed_lock=''
        return 0
    fi
    sa_visible=$(tmux show-option -qv -t "$session" @sticky-state-visible)
    sa_side=$(tmux show-option -qv -t "$session" @sticky-state-side)
    sa_width=$(tmux show-option -qv -t "$session" @sticky-state-width)
    sa_windows=$(tmux show-option -qv -t "$session" @sticky-state-layout-windows)
    # Only the plugin's canonical scalar state enters the native command queue.
    case "$sa_pane" in %*) : ;; *) fail 'Invalid local sidebar pane.' ;; esac
    case "${sa_pane#%}" in ''|*[!0-9]*) fail 'Invalid local sidebar pane.' ;; esac
    case "$sa_visible" in 0|1) : ;; *) fail 'Invalid local sidebar visibility.' ;; esac
    case "$sa_side" in left|right) : ;; *) fail 'Invalid local sidebar side.' ;; esac
    case "$sa_width" in ''|*[!0-9%]*) fail 'Invalid local sidebar width.' ;; esac
    case "$sa_windows" in *[!@0-9\ ]*) fail 'Invalid local layout registry.' ;; esac
    sa_actual=$(tmux display-message -p -t "$sa_pane" '#{session_id}')
    sa_parking=$(tmux show-option -qv -t "$sa_actual" @sticky-parking-owner)
    repair_parking
    set -- set-option -sq @sticky-state-pane "$sa_pane" \; \
        set-option -sq @sticky-state-visible "$sa_visible" \; \
        set-option -sq @sticky-state-side "$sa_side" \; \
        set-option -sq @sticky-state-width "$sa_width" \; \
        set-option -sq @sticky-state-layout-windows "$sa_windows" \; \
        set-option -pq -t "$sa_pane" @sticky-owner shared
    if [ "$sa_parking" = "$session" ]; then
        if tmux has-session -t '=__tmux_sticky_shared' 2>/dev/null; then
            fail 'The shared parking name is already in use.'
        fi
        set -- rename-session -t "$sa_actual" __tmux_sticky_shared \; \
            set-option -q -t "$sa_actual" @sticky-parking-owner shared \; "$@"
    fi
    for sa_window in $sa_windows; do
        [ "$(tmux show-option -wqv -t "$sa_window" @sticky-layout-owner 2>/dev/null || :)" = "$session" ] || continue
        set -- "$@" \; set-option -wq -t "$sa_window" @sticky-layout-owner shared
    done
    set -- "$@" \; set-option -q -t "$session" @sticky-state-pane '' \; \
        set-option -q -t "$session" @sticky-state-visible 0 \; \
        set-option -q -t "$session" @sticky-state-layout-windows ''
    command tmux "$@"
    tmux wait-for -U "$borrowed_lock"; borrowed_lock=''
}
