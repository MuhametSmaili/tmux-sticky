# tmux-sticky

A persistent tmux sidebar for any terminal application.
Hide it, reopen it, or move between windows without restarting the process.

Requires tmux 3.3a+, a POSIX shell, and standard Unix tools.

## Install

With [TPM](https://github.com/tmux-plugins/tpm), add this before your existing TPM initialization:

```tmux
set -g @plugin 'MuhametSmaili/tmux-sticky'
set -g @sticky-command 'hetki --height 100% --preview --border none'
set -g @sticky-key 'B'
```

Replace Hetki with your preferred application.
Reload your configuration, then press **prefix + I** to install.
Press **prefix + B** to show or hide the sidebar.

To try this checkout without TPM, run these commands inside tmux:

```sh
tmux set -g @sticky-command 'hetki --height 100% --preview --border none'
tmux set -g @sticky-key 'B'
./sticky.tmux
```

## Configuration

Each session has its own sidebar by default.
For one shared sidebar across sessions, add:

```tmux
set -g @sticky-follow-sessions 'on'
```

| Option                    | Default | Values                |
| ------------------------- | ------- | --------------------- |
| `@sticky-command`         | unset   | Application command   |
| `@sticky-key`             | `H`     | Unused prefix key     |
| `@sticky-side`            | `right` | `left`, `right`       |
| `@sticky-width`           | `30%`   | Percentage or columns |
| `@sticky-focus`           | `on`    | `on`, `off`           |
| `@sticky-follow-sessions` | `off`   | `on`, `off`           |

Reload your configuration after changes.
An occupied key produces an error instead of replacing your binding.
Close the shared sidebar before switching back to session-local mode.

## CLI

From the checkout:

```sh
./bin/tmux-sticky show --side left --width 40 -- yazi
./bin/tmux-sticky hide
./bin/tmux-sticky toggle
./bin/tmux-sticky status
./bin/tmux-sticky kill
```

Hide preserves the process. Kill closes it.
Use `kill --scope shared` to close the shared instance regardless of the current mode.

Hetki exits after you confirm a navigation target. The next toggle starts a new picker.

See [the reference](docs/reference.md) for manual installation, advanced flags, limitations, and troubleshooting.

[MIT license](LICENSE).
