# Shared panes follow one explicitly participating interactive client.
client_read() {
    # display-message -c selects the message recipient, not reliable format
    # context on all supported versions. Read one exact list-clients record.
    # Control-client names never enter the record stream.
    cx_record=$(tmux list-clients -F '#{?client_control_mode,,#{client_pid} #{session_id} #{pane_id} #{client_name}}' 2>/dev/null |
        STICKY_CLIENT="$1" awk '{
            pid = $1; sid = $2; pane = $3
            sub(/^[^ ]+ [^ ]+ [^ ]+ /, "")
            if ($0 == ENVIRON["STICKY_CLIENT"]) {record = "0 " sid " " pane " " pid; count++}
        } END {if (count == 1) print record}')
    [ -n "$cx_record" ] || return 1
    cx_name=$1
    read -r cx_control cx_session cx_pane cx_pid cx_extra <<EOF
$cx_record
EOF
    [ "$cx_control" = 0 ] && [ -n "$cx_session" ] && [ -n "$cx_pane" ] && [ -z "$cx_extra" ] || return 1
    case "$cx_pid" in ''|*[!0-9]*) return 1 ;; esac
}
infer_client() {
    tmux list-clients -F '#{?client_control_mode,,#{session_id} #{client_name}}' 2>/dev/null |
        awk -v sid="$session" '$1 == sid {
            sub(/^[^ ]+ /, ""); name = $0; count++
        } END {if (count == 1) print name}'
}
shared_context() {
    [ "$scope" = shared ] || return 0
    case "$action" in
        _shared-reconcile) return 0 ;;
        follow-client)
            [ "$mode" = on ] && [ -n "$(get @sticky-state-pane)" ] || exit 0
            client_read "$client" || exit 0
            [ "$(get @sticky-state-client)" = "$cx_name" ] && [ "$(get @sticky-state-client-pid)" = "$cx_pid" ] || exit 0
            session=$cx_session; target=$cx_pane; action=follow ;;
        follow)
            client=$(get @sticky-state-client)
            [ -n "$client" ] || exit 0
            client_read "$client" || exit 0
            [ "$(get @sticky-state-client-pid)" = "$cx_pid" ] && [ "$session" = "$cx_session" ] || exit 0
            target=$cx_pane ;;
        *)
            [ -n "$client" ] || client=$(infer_client)
            [ -n "$client" ] || return 0
            if ! client_read "$client"; then
                [ "$action" != status ] || return 0
                fail 'The client is missing or is a background/control client.'
            fi
            case "$action" in
                show|toggle)
                    put @sticky-state-client "$cx_name"
                    put @sticky-state-client-pid "$cx_pid"
                    if [ "${target_explicit:-0}" != 1 ]; then
                        session=$cx_session; target=$cx_pane
                    fi ;;
                status)
                    if [ -z "$(get @sticky-state-client)" ]; then
                        put @sticky-state-client "$cx_name"
                        put @sticky-state-client-pid "$cx_pid"
                    fi ;;
            esac ;;
    esac
}
