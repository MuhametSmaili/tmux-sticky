# tmux-sticky

A persistent tmux sidebar for any terminal application.

Open a file manager, task list, or system monitor once. Hide it and bring it back without restarting it.
By default, each session owns its sidebar. An optional shared mode follows your terminal across sessions too.

## Requirements

- tmux 3.3 or newer.
- A POSIX shell and standard Unix tools.
- Git and Bash for TPM installation only.

The integration suite passes on tmux 3.3a and 3.7c on macOS.
Linux verification is configured in CI but has not run yet.

## Install with TPM

Install [TPM](https://github.com/tmux-plugins/tpm) first.
Add these options before TPM initialization in `~/.tmux.conf`:

```tmux
set -g @plugin 'muhametsmaili/tmux-sticky'
set -g @sticky-command 'hetki --height 100% --preview --border none'
set -g @sticky-key 'H'
set -g @sticky-side 'right'
set -g @sticky-width '30%'

# Keep your existing TPM initialization at the bottom.
run '~/.tmux/plugins/tpm/tpm'
```

Replace the command with an application installed on your machine.
Reload the configuration, then press `prefix + I` to install the plugin.
Press `prefix + H` to open or hide the sidebar.

TPM downloads this Git repository directly. No package registry or separate release is necessary.
The repository must be pushed to GitHub before TPM can download it.

## Try the local checkout

Run these commands inside tmux, from the repository root:

```sh
tmux set-option -g @sticky-command 'hetki --height 100% --preview --border none'
./sticky.tmux
```

Now press `prefix + H`. This registers bindings and hooks in the current server.
It does not edit your configuration file or start the sidebar until you toggle it.

## Install without TPM

```sh
git clone https://github.com/muhametsmaili/tmux-sticky ~/.tmux/plugins/tmux-sticky
```

Add the command option and entrypoint to your tmux configuration:

```tmux
set -g @sticky-command 'btop'
run-shell '~/.tmux/plugins/tmux-sticky/sticky.tmux'
```

No CLI installation on `PATH` is necessary.

## Using Hetki

```tmux
set -g @sticky-command 'hetki --height 100% --preview --border none'
set -g @sticky-follow-sessions 'on'
```

This command uses no outer Hetki border and works at the default 30% width.
A wider sidebar gives the preview more space.
Use `/` to filter Hetki. Hide/show and window-follow preserve the filter and process.

Hetki currently exits when you confirm a navigation target.
The plugin cannot preserve an application after it quits. The next toggle starts a new picker.
A navigator that stays open after selection requires a persistent mode in Hetki itself.

## Choose a scope

```tmux
# Default: independent sidebar state in each project/session.
set -g @sticky-follow-sessions 'off'

# Alternative: one shared pane follows your interactive terminal.
set -g @sticky-follow-sessions 'on'
```

With `on`, the same process, filter, and visibility follow across windows and sessions.
A hidden sidebar stays hidden. The old window's unchanged layout returns when the pane leaves.
This mode suits a global navigator such as Hetki. Session-local mode suits project-specific tools.

The shared pane follows the interactive client that opened or explicitly used it.
Other interactive clients cannot pull it away merely by switching sessions.
They can take control by explicitly showing/toggling it. Background/control-client session switches are ignored.

When the shared slot is empty, `show`, `toggle`, or `status` can adopt the invoking session's existing sidebar without restarting it.
Other independent sidebars remain untouched. A window occupied by another sidebar cannot accept the shared pane.
Before switching back to `off`, close the shared instance with `./bin/tmux-sticky kill --scope shared`.
Changing the setting does not kill existing applications.

## Configuration

| Option            | Default | Meaning                                   |
| ----------------- | ------- | ----------------------------------------- |
| `@sticky-command` | unset   | Trusted shell command used on first open  |
| `@sticky-key`     | `H`     | Key after the tmux prefix                 |
| `@sticky-side`    | `right` | `left` or `right`                         |
| `@sticky-width`   | `30%`   | Percentage or fixed columns, such as `40` |
| `@sticky-focus`   | `on`    | Focus on explicit open: `on` or `off`     |
| `@sticky-follow-sessions` | `off` | `off`: per session; `on`: one shared pane |

An occupied key produces an error instead of replacing the existing binding.
Configuration reload updates owned hooks and bindings without restarting the application.
Set `@sticky-key` and `@sticky-follow-sessions` globally. The other options support session overrides:

```tmux
set -t work @sticky-command 'yazi'
set -t work @sticky-width '40'
```

Command changes apply after the old application exits or you run `kill`.
Hiding is not killing.

## Standalone CLI

Use `./bin/tmux-sticky` locally, or add `bin/` to your `PATH`.

```sh
./bin/tmux-sticky toggle --side left --width 40 -- yazi
./bin/tmux-sticky hide
./bin/tmux-sticky show
./bin/tmux-sticky status
./bin/tmux-sticky kill
./bin/tmux-sticky cleanup
```

`show` and `hide` are idempotent. `toggle` switches visibility.
`kill` closes the application. `status` reports state, scope, owner, pane ID, and process PID.
Shared status also reports its controlling client. Its owner label is `shared`, not a project session.
`cleanup` removes orphan parking sessions and stale application state.

Pass `--target %pane` to choose an invoking pane explicitly.
Use `--scope session` or `--scope shared` to inspect or close a specific mode regardless of the global setting.
Use `--client CLIENT_NAME` to explicitly choose an interactive controller for shared operations.
Use `--focus off` to retain focus on the main pane.
CLI options override configuration for that invocation. Omitted options use the configured values or defaults.
Size and side apply when inserting a pane. If it is already in the target window, `show` leaves its geometry unchanged.
The requested size and side are remembered for the next move. Hide and show to apply them immediately.

Multiple arguments after `--` execute directly through tmux.
A single argument is a trusted tmux shell-command string:

```sh
./bin/tmux-sticky show -- 'exec my-tool --file "a b.txt"'
```

The CLI does not use `eval`. Do not put untrusted input in shell-command strings.
Do not use shell aliases or functions in commands unless you explicitly launch the shell that defines them.

Automatic following, exit cleanup, and edit tracking require loading `sticky.tmux`, with or without TPM.
Without that entrypoint, the CLI supports explicit `show --target %pane` movement and `cleanup`.
Session-local `follow SESSION_ID` works manually. Shared following requires a bound interactive client.

## Behavior and limits

- Default mode has one sidebar per session. Shared mode has one sidebar per tmux server, directed by one interactive client.
- Hiding parks the pane in a detached `__tmux_sticky_*` session. That session contains only the parked pane.
- Internal parking sessions can appear in session pickers. Do not attach to or edit them.
- Reopening moves the same process back. Application memory, history, and pane contents remain.
- The initial working directory comes from the invoking pane. Window/session changes do not change the application's directory.
- Automatic following does not select the sidebar or steal focus from the destination pane.
- Grouped sessions and linked windows are not supported.
- Session/window-local hooks can shadow the plugin's global hooks. Following, exit cleanup, and edit tracking require that those hooks remain inherited.
  The plugin preserves local hook arrays instead of replacing them.
- Zoomed windows require unzooming before movement. A refused follow leaves the sidebar in its previous window.
- Narrow windows must leave at least five sidebar columns and ten main columns.
- Hiding or moving the only pane out of its session is refused. Create another window first. Owned parking sessions are exempt.
- Main panes shrink while the sidebar is visible. When it leaves, an unchanged layout returns to its original proportions.
- Layout restoration checks the entire pane tree, IDs, dimensions, and offsets. Detected edits, window resizing, or unsupported layouts skip restoration.
- Removing the sidebar after a manual edit follows tmux's native resizing behavior. The next open starts a fresh layout snapshot.
- Moving panes can redraw the application. Flicker-free movement is not guaranteed.
- Session-local persistence ends when its owning session exits, even if parked.
- Shared persistence is independent of sessions it has already left. Killing its current visible host session still closes the pane.
  Hide the shared pane before closing that project to preserve it. App/server exit always ends persistence.
- Stopped or forcibly killed handlers can leave a tmux lock held. After confirming no handler is active, unlock with `tmux wait-for -U 'tmux-sticky-N'`.
  Replace `N` with the numeric part of the owning session ID. Shared operations use `tmux-sticky-shared`.

## Troubleshooting

Run `./bin/tmux-sticky status` and `./bin/tmux-sticky cleanup` inside the affected session.
Errors from key bindings appear in tmux messages. Use `tmux show-messages` to inspect them.

If tmux cannot find an application, use its absolute path in `@sticky-command`.
tmux background commands do not read your interactive shell configuration.

Before uninstalling, close the shared instance with `kill --scope shared` and independent instances with `kill --scope session`.
Remove the plugin configuration. Existing hooks and bindings remain in the current server until removed or the server exits normally.

## Development

Tests require Python 3 and tmux. Lint requires ShellCheck.

```sh
make test
make lint
# Optional: test your installed Hetki in an isolated environment.
make smoke-hetki
make smoke-shared-hetki
```

Tests use temporary sockets and empty tmux configuration files.
They do not connect to your normal tmux server.
Coverage includes process identity, automatic following, real prefix input, reloads, cleanup, quoting, concurrency, interruption recovery, and layout refusal.
The optional Hetki check also isolates HOME, configuration, cache, and its background service.

## License

MIT. See [LICENSE](LICENSE).
