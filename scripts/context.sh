# Resolve the invocation separately from the lifetime/ownership of its state.
scope='' scope_explicit=0 client='' session='' target=${TMUX_PANE:-}
mode=$(tmux show-option -gqv @sticky-follow-sessions)
case "$mode" in ''|off) mode=off ;; on) : ;; *) fail '@sticky-follow-sessions must be on or off.' ;; esac
side='' width='' focus=''
case "$action" in
    follow-client)
        [ "$mode" = on ] || exit 0
        [ "$#" -eq 1 ] || exit 2
        client=$1; shift; scope=shared; target='' ;;
    follow|_reconcile)
        [ "$#" -eq 1 ] || { usage >&2; exit 2; }
        session=$1; shift
        tmux has-session -t "$session" 2>/dev/null || exit 0
        session=$(tmux display-message -p -t "$session" '#{session_id}')
        [ "$action" != _reconcile ] || scope=session ;;
    _shared-reconcile) [ "$#" -eq 0 ] || exit 2; scope=shared ;;
esac
while [ "$#" -gt 0 ]; do
    case "$1" in
        --target|--side|--width|--focus|--scope|--client)
            [ "$#" -ge 2 ] || fail "Missing value for $1"
            case "$1" in
                --target) target=$2 ;; --side) side=$2 ;;
                --width) width=$2 ;; --focus) focus=$2 ;;
                --scope) scope=$2; scope_explicit=1 ;; --client) client=$2 ;;
            esac
            shift 2 ;;
        --) shift; break ;;
        *) fail "Unknown option: $1" ;;
    esac
done
if [ -z "$scope" ]; then
    scope=session
    [ "$mode" != on ] || scope=shared
fi
case "$scope" in session|shared) : ;; *) fail 'Scope must be session or shared.' ;; esac
if [ -z "$session" ] && [ "$action" != _shared-reconcile ] && [ "$action" != follow-client ]; then
    [ -n "$target" ] || fail 'Run inside tmux or pass --target %pane.'
    identity=$(tmux display-message -p -t "$target" '#{session_id} #{pane_id}') || fail 'Target pane does not exist.'
    session=${identity%% *}; target=${identity#* }
    [ -n "$session" ] && [ -n "$target" ] || fail 'Target pane does not exist.'
    owner=$(tmux show-option -pqv -t "$target" @sticky-owner 2>/dev/null || :)
    if [ "$scope" = session ] && [ -n "$owner" ]; then
        if [ "$owner" = shared ]; then
            [ "$scope_explicit" = 1 ] || scope=shared
        else session=$owner; fi
    fi
fi
state_owner=$session
state_flag=''
if [ "$scope" = shared ]; then state_owner=shared; state_flag=s; fi
lock="tmux-sticky-${state_owner#\$}"
