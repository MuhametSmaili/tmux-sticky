# tmux-sticky

A process-preserving tmux sidebar for terminal applications.

Each session owns one sidebar. Hiding parks the pane instead of restarting the application.
The pane follows window changes within its session.

## Local use

Requirements: tmux 3.3+, a POSIX shell, and standard Unix tools.

From the repository root, inside tmux:

```sh
tmux set -g @sticky-command 'hetki --height 100% --preview'
./sticky.tmux
```

Press prefix + H to toggle. Set @sticky-key to an unused key if H is already bound.
Loading the executable entrypoint registers bindings and hooks without opening the application.
TPM can load the same root entrypoint.

## CLI

```sh
./bin/tmux-sticky show --side right --width 30% -- btop
./bin/tmux-sticky hide
./bin/tmux-sticky show
./bin/tmux-sticky status
./bin/tmux-sticky kill
./bin/tmux-sticky cleanup
```

Configuration supports @sticky-command, @sticky-key, @sticky-side, @sticky-width, and @sticky-focus.
The command inherits the invoking pane's directory on first launch.
Hide/show preserves process identity. Kill intentionally closes the application.
Automatic following and exit cleanup require loading sticky.tmux.

## Limits

Grouped sessions, linked windows, and zoomed/narrow destinations are refused.
tmux can redistribute neighboring pane sizes when the sidebar leaves.
This initial version does not restore the original layout.

## Development

Tests require Python 3 and tmux. Lint requires ShellCheck.

```sh
make check
make smoke-hetki
```

Tests use isolated tmux servers, not the user's normal server.

## License

MIT. See [LICENSE](LICENSE).
