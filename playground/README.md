# CDC Worker command playground

Self-contained `cdc-playground.html` — an **in-browser fake shell** (xterm.js,
no server, no jar) where a newcomer can figure out how to use CDC Worker by
poking at it. Three modes, all fed from the **real** `java -jar cdc-worker.jar`
output so the sandbox never lies:

- **command mode** — type any `--help-*` and see the actual captured output.
- **`tutorial <preset>`** — walk a runbook step-by-step (vimtutor-style): each
  shell command is one step, with a plausible fake result per command type.
- **`start` (wizard)** — answers-driven: "откуда → куда → где запускать?" plus
  "источник/приёмник уже подняты?" → assembles a full plan: what to download
  from Customer Zone, what to stand up, and the launch command. Never says the
  word "preset" — the user thinks in "PostgreSQL / очередь", not internals.

## Build

```bash
make help-playground                         # from repo root; picks JDK 21
JAVA_HOME=<jdk21> PLUGINS_DIR=<plugins> playground/build.sh [path/to/cdc-worker.jar]
```

Bakes `../cdc-playground.html` (git-ignored — regenerate, don't commit).
Connectors whose plugin isn't installed are skipped; `make plugins` first for
the full set of `--help-*-params`.

## Files (the source of truth — the HTML is generated)

- `build.sh` — captures every `--help-*` into a temp dir, assembles 3 JSON,
  bakes the HTML.
- `parse_runbook.py` — splits a runbook into steps (one shell command each,
  heredocs and `\`-continuations kept whole).
- `build_tutorials.py` — steps + a fake per-command output → `tutorials.json`.
- `build_snippets.py` — carves runbooks into role sections (source_pg / sink_pg
  / tqe / worker / …) so the wizard can show "how to stand up the source" →
  `snippets.json`.
- `gen_html.py` — the page template; splices `commands` / `tutorials` /
  `snippets` JSON in and writes the final HTML.
