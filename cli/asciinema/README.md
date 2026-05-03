# speca-cli demo recordings

This folder hosts the [asciinema](https://asciinema.org/) recordings linked
from the main `cli/README.md`. Recordings are **not** generated in CI —
reviewers record them locally, upload to asciinema.org, and add the URL to
`cli/README.md` (Polish & customization section).

## Why asciinema

asciinema captures terminal sessions as text + timing (`.cast` files), so
the playback page is fully copy-pasteable and reads as crisp ANSI even on
high-DPI displays. It's the convention used by every other Ink-based CLI
(Crush, Plandex) and by Anthropic's own Claude Code docs.

## Install asciinema

| OS | Command |
|---|---|
| macOS | `brew install asciinema` |
| Linux (Debian/Ubuntu) | `sudo apt install asciinema` |
| Linux (Fedora/RHEL) | `sudo dnf install asciinema` |
| Linux (Arch) | `sudo pacman -S asciinema` |
| Windows | asciinema's recorder is POSIX-only. Record from WSL2 (`wsl -d Ubuntu`) or run `speca-cli` inside Windows Terminal under WSL2 and record there. Native Windows users can fall back to [terminalizer](https://github.com/faressoft/terminalizer) — output looks similar but is not interchangeable with the `.cast` format. |

Verify with `asciinema --version`.

## Demo scenarios

Three short flows are recorded for the README. Each one should be **under
90 seconds** so the embedded player loads quickly. Use a 100×30 terminal
(`stty cols 100 rows 30`) for consistent framing.

### 1. `doctor` — fresh-laptop sanity check

```bash
asciinema rec doctor.cast \
  --title "speca doctor on a fresh laptop" \
  --idle-time-limit 1.5

# inside the recording shell
clear
speca doctor
exit
```

Expected: the four green check rows, then the auth row (warn or fail
depending on whether the recorder has run `speca auth login`).

### 2. `init` — wizard happy path

```bash
asciinema rec init.cast \
  --title "speca init wizard" \
  --idle-time-limit 1.5

# inside the recording shell
clear
mkdir -p /tmp/speca-demo && cd /tmp/speca-demo
speca init   # walk through every wizard step with realistic answers
ls outputs/  # show the two generated JSON files
exit
```

Expected: `outputs/TARGET_INFO.json` and `outputs/BUG_BOUNTY_SCOPE.json`
land in the demo dir.

### 3. `browse` — finding browser (M4+)

```bash
asciinema rec browse.cast \
  --title "speca browse — finding browser" \
  --idle-time-limit 1.5

# inside the recording shell
clear
cd path/to/finished/audit          # one with outputs/04_PARTIAL_*.json
speca browse                       # land on the table view
# press: down down down  (navigate)
# press: f severity:critical enter (filter)
# press: enter                     (open detail pane)
# press: q                         (quit)
exit
```

Expected: filtered table, detail-pane peek, clean exit. This scenario
depends on M4 having landed; record once `feat/m4-finding-browser` is
merged.

## Upload

```bash
asciinema upload doctor.cast
# → prints https://asciinema.org/a/XXXXXX

asciinema upload init.cast
asciinema upload browse.cast
```

The first upload from a new machine will print a one-time claim URL —
follow it to associate the recording with the maintainer asciinema
account.

## Add the URL to README

Replace the `<TODO>` placeholder under the **Demos** subsection of
`cli/README.md` with the asciinema embed snippet asciinema.org generates
for each recording, e.g.

```markdown
[![asciicast](https://asciinema.org/a/XXXXXX.svg)](https://asciinema.org/a/XXXXXX)
```

Commit message convention: `docs(cli): asciinema link for <scenario>`.

## Re-recording policy

Re-record a `.cast` file when:

- the corresponding subcommand's UX changes (column count, key bindings,
  default theme),
- the wizard's question set changes (init only),
- a new dependency appears in the `doctor` table.

Do **not** re-record for cosmetic theme tweaks — that's what `--theme` is
for, and a single dark-mode recording covers the visual range.
