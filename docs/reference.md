# Reference

## Manual installation

Clone the repository:

```sh
git clone https://github.com/MuhametSmaili/tmux-sticky ~/.tmux/plugins/tmux-sticky
```

Add these lines to your tmux configuration:

```tmux
set -g @sticky-command 'btop'
run-shell '~/.tmux/plugins/tmux-sticky/sticky.tmux'
```

The plugin itself uses a POSIX shell. TPM also requires Git and Bash, including Bash during plugin loading.

## Commands and flags

Use `bin/tmux-sticky --help` for usage.
The CLI works from the checkout without installation on PATH.

- `--target %pane` explicitly selects the destination pane, even with a bound client.
- `--scope session|shared` selects the instance regardless of the configured mode.
- `--client CLIENT_NAME` selects the interactive controller for shared operations.
- `--side left|right`, `--width 30%|40`, and `--focus on|off` override configuration for one invocation.
- `cleanup` reconciles stale state and removes owned orphan parking sessions.

Side and width apply at the next insertion. An already visible pane does not resize on `show`.
Command changes apply after the existing application exits or you close it with `kill`.
The application keeps its initial working directory when it moves.

Multiple arguments after `--` execute directly. A single argument is a trusted shell-command string.
Do not interpolate untrusted input into that string. Shell aliases and functions are not available unless you launch their shell.

Set the key and session-following mode globally. Other options support session overrides:

```tmux
set -t work @sticky-command 'yazi'
set -t work @sticky-width '40'
```

## Shared mode

The shared pane follows its controlling interactive client.
Another client can take control with an explicit `show` or `toggle`, not merely by switching sessions.
Control clients cannot claim or move it. A hidden sidebar stays hidden.

An empty shared slot can adopt the invoking session's existing sidebar through `show`, `toggle`, or `status`.
Other session-owned applications remain untouched. Changing modes does not close them automatically.

## Limits

- Grouped sessions and linked windows are unsupported. Unzoom the destination before movement.
- A window must leave at least five sidebar columns and ten main columns.
- Moving the only pane out of a normal session is refused. Create another window first.
- Unchanged main layouts return to their original proportions. Detected edits, resizing, or unsupported layouts skip restoration.
- Pane movement can redraw the application. Flicker-free movement is not guaranteed.
- Session-owned persistence ends when its owner exits. A shared pane survives sessions it has already left.
- Killing the shared pane's current host session closes it. Hide the pane before closing that project to preserve it.
- Parked panes live in detached `__tmux_sticky_*` sessions. Do not attach to or edit those sessions.
- Automatic following, exit cleanup, and edit tracking require loading `sticky.tmux`.
- Session/window-local hook arrays can shadow the plugin's global hooks. The plugin preserves those local arrays.

## Troubleshooting

Inspect `bin/tmux-sticky status`, `bin/tmux-sticky cleanup`, and `tmux show-messages`.
Use an absolute application path if tmux cannot find the command.

Stopped or forcibly killed handlers can leave locks held.
Resume or terminate a stopped handler first. Confirm that no handler is active before unlocking.
Scope locks use `tmux-sticky-N` (numeric session ID) or `tmux-sticky-shared`.
Unlock only the affected channel with `tmux wait-for -U CHANNEL`.

Before uninstalling, close shared and session-owned instances with `kill --scope shared` and `kill --scope session`.
Remove the plugin configuration. Existing hooks and bindings remain until removed or the server exits.

## Development

Run `make check` with Python 3, tmux, and ShellCheck installed.
The tests use isolated tmux servers, not your normal server.

Optional actual-application checks: `make smoke-hetki` and `make smoke-shared-hetki`.
These checks isolate Hetki's HOME, configuration, cache, and background service.
