# Window snapshots are scope-owned; claims and cleanup run in native queues.
layout_prepare() (
    lp_window=$1
    [ -n "$lp_window" ] && [ "$(tmux display-message -p -t "$lp_window" '#{window_id}')" = "$lp_window" ] || fail 'Destination window no longer exists.'
    lp_owner=$(tmux show-option -wqv -t "$lp_window" @sticky-layout-owner)
    [ -z "$lp_owner" ] || [ "$lp_owner" = "$state_owner" ] || fail 'Window layout belongs to another sidebar.'
    lp_windows=$(get @sticky-state-layout-windows)
    case " $lp_windows " in
        *" $lp_window "*) : ;;
        *) lp_windows="${lp_windows:+$lp_windows }$lp_window" ;;
    esac
    # Only generated window IDs belong in this native command argument.
    case "$lp_windows" in *[!@0-9\ ]*) fail 'Invalid saved window index.' ;; esac
    lp_guard="#{||:#{==:#{@sticky-layout-owner},},#{==:#{@sticky-layout-owner},$state_owner}}"
    lp_claim="set-option -wq -t '$lp_window' @sticky-layout-owner '$state_owner';
        set-option -wq -t '$lp_window' @sticky-layout-before '';
        set-option -wq -t '$lp_window' @sticky-layout-after '';
        set-option -wq -t '$lp_window' @sticky-layout-pane '';
        set-option -wq -t '$lp_window' @sticky-layout-dirty '';"
    if [ "$scope" = shared ]; then
        lp_claim="$lp_claim set-option -sq @sticky-state-layout-windows '$lp_windows';"
    else
        lp_claim="$lp_claim set-option -q -t '$session' @sticky-state-layout-windows '$lp_windows';"
    fi
    # Other scope handlers cannot interleave between this guard and claim.
    lp_result=$(command tmux if-shell -Ft "$lp_window" "$lp_guard" \
        "$lp_claim display-message -p claimed" 'display-message -p busy') || fail 'Could not claim the destination window.'
    [ "$lp_result" = claimed ] || fail 'Window layout belongs to another sidebar.'
)

layout_checkpoint() (
    # Adjacent pane/sidebar resizing can cancel out when the sidebar leaves.
    # Observe edits before removal, not just the resulting main geometry.
    for lc_window in $(get @sticky-state-layout-windows); do
        lc_owner=$(tmux show-option -wqv -t "$lc_window" @sticky-layout-owner 2>/dev/null || :)
        [ "$lc_owner" = "$state_owner" ] || continue
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
        [ "$lr_owner" = "$state_owner" ] || continue
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
        lr_commands=''
        if [ -z "$lr_dirty" ] && [ -n "$lr_before" ] && [ -n "$lr_after" ] && [ -n "$lr_pane" ]; then
            lr_expected=$(printf '%s\n' "$lr_after" | awk -v pane="${lr_pane#%}" -f "$ROOT/scripts/layout-remove.awk") || lr_expected=''
            lr_current=$(tmux display-message -p -t "$lr_window" '#{window_zoomed_flag} #{window_layout}')
            if [ -n "$lr_expected" ] && [ "${lr_current%% *}" = 0 ] && [ "${lr_current#*,}" = "$lr_expected" ]; then
                # Recheck user geometry at application time, not just in shell.
                lr_guard='#{&&:#{==:#{window_zoomed_flag},0},#{&&:#{==:#{@sticky-layout-dirty},},#{==:#{window_layout},#{@sticky-layout-check}}}}'
                lr_commands="set-option -wq -t '$lr_window' @sticky-layout-check '${lr_current#* }';
                    if-shell -Ft '$lr_window' '$lr_guard' \"select-layout -t '$lr_window' '$lr_before'\";"
            fi
        fi
        for lr_key in owner before after pane dirty check; do
            lr_commands="$lr_commands set-option -wqu -t '$lr_window' '@sticky-layout-$lr_key';"
        done
        # Restoration and metadata removal must not erase a later scope's claim.
        command tmux if-shell -Ft "$lr_window" \
            "#{==:#{@sticky-layout-owner},$state_owner}" "$lr_commands" >/dev/null || :
    done
    put @sticky-state-layout-windows "$lr_keep" 2>/dev/null || :
)
