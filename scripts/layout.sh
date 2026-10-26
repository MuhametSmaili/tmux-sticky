# Window-local snapshots, indexed by the owning session under its existing lock.
layout_prepare() (
    lp_window=$1
    [ -n "$lp_window" ] && [ "$(tmux display-message -p -t "$lp_window" '#{window_id}')" = "$lp_window" ] || fail 'Destination window no longer exists.'
    lp_owner=$(tmux show-option -wqv -t "$lp_window" @sticky-layout-owner)
    [ -z "$lp_owner" ] || [ "$lp_owner" = "$session" ] || fail 'Window layout belongs to another sidebar.'
    lp_before=$(tmux display-message -p -t "$lp_window" '#{window_layout}')
    [ -n "$lp_before" ] || fail 'Could not read the destination layout.'
    command tmux set-option -wq -t "$lp_window" @sticky-layout-owner "$session" \; \
        set-option -wq -t "$lp_window" @sticky-layout-before "$lp_before" \; \
        set-option -wq -t "$lp_window" @sticky-layout-after '' \; \
        set-option -wq -t "$lp_window" @sticky-layout-pane '' \; \
        set-option -wq -t "$lp_window" @sticky-layout-dirty ''
    lp_windows=$(get @sticky-state-layout-windows)
    case " $lp_windows " in
        *" $lp_window "*) : ;;
        *) put @sticky-state-layout-windows "${lp_windows:+$lp_windows }$lp_window" ;;
    esac
)

layout_checkpoint() (
    # Adjacent pane/sidebar resizing can cancel out when the sidebar leaves.
    # Observe edits before removal, not just the resulting main geometry.
    for lc_window in $(get @sticky-state-layout-windows); do
        lc_owner=$(tmux show-option -wqv -t "$lc_window" @sticky-layout-owner 2>/dev/null || :)
        [ "$lc_owner" = "$session" ] || continue
        lc_pane=$(tmux show-option -wqv -t "$lc_window" @sticky-layout-pane)
        lc_after=$(tmux show-option -wqv -t "$lc_window" @sticky-layout-after)
        [ -n "$lc_pane" ] && [ -n "$lc_after" ] || continue
        lc_actual=$(tmux display-message -p -t "$lc_pane" '#{window_id}' 2>/dev/null || :)
        [ "$lc_actual" = "$lc_window" ] || continue
        lc_current=$(tmux display-message -p -t "$lc_window" '#{window_layout}')
        [ "$lc_current" = "$lc_after" ] || tmux set-option -wq -t "$lc_window" @sticky-layout-dirty edited
    done
)

layout_reconcile() (
    lr_keep=''
    for lr_window in $(get @sticky-state-layout-windows); do
        case "$lr_window" in @*) : ;; *) continue ;; esac
        [ "$(tmux display-message -p -t "$lr_window" '#{window_id}' 2>/dev/null || :)" = "$lr_window" ] || continue
        lr_owner=$(tmux show-option -wqv -t "$lr_window" @sticky-layout-owner 2>/dev/null || :)
        [ "$lr_owner" = "$session" ] || continue
        lr_pane=$(tmux show-option -wqv -t "$lr_window" @sticky-layout-pane)
        lr_actual=''
        [ -z "$lr_pane" ] || lr_actual=$(tmux display-message -p -t "$lr_pane" '#{window_id}' 2>/dev/null || :)
        if [ -n "$lr_pane" ] && [ "$lr_actual" = "$lr_window" ]; then
            lr_keep="${lr_keep:+$lr_keep }$lr_window"
            continue
        fi
        lr_before=$(tmux show-option -wqv -t "$lr_window" @sticky-layout-before)
        lr_after=$(tmux show-option -wqv -t "$lr_window" @sticky-layout-after)
        lr_dirty=$(tmux show-option -wqv -t "$lr_window" @sticky-layout-dirty)
        if [ -z "$lr_dirty" ] && [ -n "$lr_before" ] && [ -n "$lr_after" ] && [ -n "$lr_pane" ]; then
            lr_expected=$(printf '%s\n' "$lr_after" | awk -v pane="${lr_pane#%}" -f "$ROOT/scripts/layout-remove.awk") || lr_expected=''
            lr_current=$(tmux display-message -p -t "$lr_window" '#{window_zoomed_flag} #{window_layout}')
            # Compare the entire tree: pane IDs, topology, sizes, and offsets.
            # Any user edit or terminal resize invalidates the old snapshot.
            if [ -n "$lr_expected" ] && [ "${lr_current%% *}" = 0 ] && [ "${lr_current#*,}" = "$lr_expected" ]; then
                tmux select-layout -t "$lr_window" "$lr_before" >/dev/null || :
            fi
        fi
        for lr_key in owner before after pane dirty; do
            tmux set-option -wqu -t "$lr_window" "@sticky-layout-$lr_key" 2>/dev/null || :
        done
    done
    put @sticky-state-layout-windows "$lr_keep" 2>/dev/null || :
)
