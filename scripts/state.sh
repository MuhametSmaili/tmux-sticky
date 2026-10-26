# Runtime state is session-local by default, server-scoped for a shared pane.
get() {
    if [ "$scope" = shared ]; then tmux show-option -sqv "$1" 2>/dev/null || :
    else tmux show-option -qv -t "$session" "$1" 2>/dev/null || :; fi
}
put() {
    if [ "$scope" = shared ]; then tmux set-option -sq "$1" "$2"
    else tmux set-option -q -t "$session" "$1" "$2"; fi
}
config() { tmux show-option -Aqv -t "$session" "$1" 2>/dev/null || :; }
option() {
    case "$1" in
        @sticky-state-*) value=$(get "$1") ;;
        *) value=$(config "$1") ;;
    esac
    printf '%s' "${value:-$2}"
}
