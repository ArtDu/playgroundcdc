# CDC Worker help site

Static, self-contained HTML rendering of every `java -jar cdc-worker.jar --help-*`
output — so someone who can't run the jar or docker can still browse the help
(connector params, transforms, ADRs, presets, runbooks).

## Build

```bash
make help-site                       # from repo root; picks JDK 21 automatically
make help-site PLUGINS_DIR=/path      # custom connector plugins dir (default ./plugins)
```

Or directly:

```bash
JAVA_HOME=<jdk21> PLUGINS_DIR=<plugins> cdc-worker/help-site/build.sh [path/to/cdc-worker.jar]
```

This dumps every `--help-*` and bakes it into a single **`cdc-help.html`** —
open it by double-click (no server) or publish it to GitHub Pages. Connectors
whose plugin isn't installed are skipped; run `make plugins` first for the full
set.

## Files

- `build.sh` — runs the jar, dumps help, bakes `cdc-help.html`.
- `template.html` — page shell with inlined `marked.js`; `build.sh` splices the
  docs in at the `/*__DOCS__*/[]` marker.
- `fix-tables.py` — repairs markdown tables whose cells contain literal newlines
  (some connector param descriptions), and drops duplicate connector blocks.
- `cdc-help.html` — generated output (git-ignored; regenerate with `make help-site`).
