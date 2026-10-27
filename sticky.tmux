#!/bin/sh
# TPM entrypoint. Safe to run again after reloading tmux.conf.
set -eu
# A trailing semicolon is a tmux command separator even inside a shell argv.
# Add the protocol escape without changing shell argument boundaries.
tmux() (
    remaining=$#
    while [ "$remaining" -gt 0 ]; do
        argument=$1; shift
        case "$argument" in *';') argument="${argument%;}\\;" ;; esac
        set -- "$@" "$argument"
        remaining=$((remaining - 1))
    done
    command tmux "$@"
)

ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
RUNNER="$ROOT/scripts/run.sh"
# shellcheck source=scripts/layout-format.sh
. "$ROOT/scripts/layout-format.sh"

fail() {
    printf 'tmux-sticky: %s\n' "$*" >&2
    tmux display-message "tmux-sticky: $*" 2>/dev/null || :
    exit 1
}
# run-shell expands tmux formats. Escape literal hashes in installation paths.
runner=$(layout_quote "$(printf '%s' "$RUNNER" | sed 's/#/##/g')")

register_hook() {
    hook=$1; action=$2
    index=$(tmux show-option -gqv "@sticky-internal-hook-$hook")
    case "$index" in ''|*[!0-9]*) index=30000 ;; esac
    while :; do
        existing=$(tmux show-option -gqv "${hook}[$index]" 2>/dev/null || :)
        case "$existing" in
            ''|*"tmux-sticky/$hook"*) break ;;
        esac
        index=$((index + 1))
        [ "$index" -le 31000 ] || fail "No free hook entry for $hook."
    done
    if [ "${3:-}" = direct ]; then command=$action
    else command="run-shell -b $(layout_quote "exec $runner $action # tmux-sticky/$hook")"; fi
    tmux set-hook -g "${hook}[$index]" "$command"
    tmux set-option -gq "@sticky-internal-hook-$hook" "$index"
}

binding() {
    # Let tmux normalize modifier aliases without touching prefix bindings.
    probe="__tmux_sticky_probe_$$"
    tmux bind-key -T "$probe" "$1" display-message probe || return 1
    canonical=$(tmux list-keys | STICKY_TABLE="$probe" awk '{
        for (i = 1; i < NF; i++) if ($i == "-T") {
            if ($(i + 1) == ENVIRON["STICKY_TABLE"]) print $(i + 2)
            break
        }
    }')
    [ -n "$canonical" ] || return 1
    tmux unbind-key -a -T "$probe"
    # Listing the table also works when a key filter omits command-form output.
    tmux list-keys | STICKY_KEY="$canonical" awk '
        { for (i = 1; i < NF; i++) if ($i == "-T") {
            if ($(i + 1) == "prefix" && $(i + 2) == ENVIRON["STICKY_KEY"]) print
            break
        } }
    '
}
key=$(tmux show-option -gqv @sticky-key)
key=${key:-H}
old=$(tmux show-option -gqv @sticky-internal-key)
existing=$(binding "$key")
case "$existing" in
    ''|*tmux-sticky/toggle*) : ;;
    *) fail "Prefix key $key is already bound. Set @sticky-key to another key." ;;
esac
previous=''
if [ -n "$old" ] && [ "$old" != "$key" ]; then previous=$(binding "$old"); fi
tmux bind-key -T prefix -N 'Toggle persistent sidebar' "$key" run-shell -b "exec $runner toggle --target '#{pane_id}' --client #{q:client_name} # tmux-sticky/toggle"
# Equivalent spellings refer to the same binding. Do not unbind it afterward.
if [ -n "$previous" ] && [ "$previous" != "$existing" ]; then
    case "$previous" in *tmux-sticky/toggle*) tmux unbind-key -T prefix "$old" ;; esac
fi
tmux set-option -gq @sticky-internal-key "$key"

register_hook session-window-changed "follow '#{hook_session}'"
register_hook client-session-changed "follow-client #{q:hook_client}"
register_hook pane-exited cleanup
register_hook pane-died cleanup
register_hook after-kill-pane cleanup
register_hook session-closed cleanup
# Mark edits in tmux itself, before asynchronous exit cleanup can restore.
layout_same_format='#{==:#{m/r:^[0-9a-fA-F],#{window_layout}},#{m/r:^[0-9a-fA-F],#{@sticky-layout-after}}}'
layout_difference="#{?$layout_same_format,#{!=:$layout_format,#{@sticky-layout-after}},#{||:#{==:#{@sticky-layout-signature},},#{!=:$layout_signature,#{@sticky-layout-signature}}}}"
layout_changed="#{&&:#{@sticky-layout-after},#{&&:$layout_difference,#{m:*#{@sticky-layout-pane} *,#{P:#{pane_id} }}}}"
register_hook window-layout-changed "if-shell -F $(layout_quote "$layout_changed") $(layout_quote 'set-option -wq @sticky-layout-dirty tmux-sticky/window-layout-changed')" direct
