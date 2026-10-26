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

fail() {
    printf 'tmux-sticky: %s\n' "$*" >&2
    tmux display-message "tmux-sticky: $*" 2>/dev/null || :
    exit 1
}
quote() {
    printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"
}
# run-shell expands tmux formats. Escape literal hashes in installation paths.
runner=$(quote "$(printf '%s' "$RUNNER" | sed 's/#/##/g')")

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
    command="exec $runner $action # tmux-sticky/$hook"
    tmux set-hook -g "${hook}[$index]" "run-shell -b $(quote "$command")"
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
tmux bind-key -T prefix -N 'Toggle persistent sidebar' "$key" run-shell -b "exec $runner toggle --target '#{pane_id}' # tmux-sticky/toggle"
# Equivalent spellings refer to the same binding. Do not unbind it afterward.
if [ -n "$previous" ] && [ "$previous" != "$existing" ]; then
    case "$previous" in *tmux-sticky/toggle*) tmux unbind-key -T prefix "$old" ;; esac
fi
tmux set-option -gq @sticky-internal-key "$key"

register_hook session-window-changed "follow '#{hook_session}'"
register_hook pane-exited cleanup
register_hook pane-died cleanup
register_hook session-closed cleanup
