#!/bin/sh
# Present runtime errors in tmux rather than losing stderr from background jobs.
set -eu
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
if ! message=$("$ROOT/bin/tmux-sticky" "$@" 2>&1); then
    tmux display-message "$message" 2>/dev/null || printf '%s\n' "$message" >&2
fi
