#!/usr/bin/env bash
# Bake the CDC Worker command playground into ONE self-contained
# cdc-playground.html — an in-browser fake shell (xterm.js) where a user can:
#   * run every --help-* command and see the REAL captured output,
#   * walk a runbook step-by-step (tutorial mode, vimtutor-style),
#   * answer a wizard ("откуда → куда → где запускать?") that assembles a full
#     plan: what to download from Customer Zone, what to stand up, how to launch.
#
# All content is captured from the real `java -jar cdc-worker.jar --help-*`, so
# the sandbox never lies. Regenerate whenever the worker's help output changes.
#
# Usage:
#   JAVA_HOME=/path/to/jdk21 ./build.sh [path/to/cdc-worker.jar]
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
jar="${1:-$here/../../target/cdc-worker-1.0.0-SNAPSHOT.jar}"
java="${JAVA_HOME:+$JAVA_HOME/bin/}java"
py="${PYTHON:-python3}"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
dumps="$tmp/dumps"; mkdir -p "$dumps"
outhtml="$here/../cdc-playground.html"   # sits next to cdc-help.html in help-site/

[ -f "$jar" ] || { echo "jar not found: $jar (build with 'make install-jar')" >&2; exit 1; }

plugins="${PLUGINS_DIR:-$here/../../../plugins}"
scan=()
[ -d "$plugins" ] && scan=(--scan-plugins="$(cd "$plugins" && pwd)") \
  || echo "warning: plugins dir not found at $plugins — connector *-params will be skipped" >&2

# dump <key> -- <jar args...>  → writes $dumps/<key>.txt (skips empty/failed runs,
# e.g. a connector whose plugin isn't installed, or an unsupported --simple combo).
# NOTE: --scan-plugins is passed ONLY by dumpp (param help). It must NOT be added to
# runbook/overview commands — with plugins on the classpath the worker resolves a
# DIFFERENT code path and --help-<preset> stops printing the runbook.
dump() {
  local key="$1"; shift; [ "$1" = "--" ] && shift
  local f="$dumps/$key.txt"
  if "$java" -jar "$jar" "$@" >"$f" 2>/dev/null && [ -s "$f" ] \
     && ! grep -qE 'Connector not found|Unknown preset' "$f"; then :; else rm -f "$f"; fi
}
# dumpp — like dump, but WITH --scan-plugins (connector *-params need the plugins).
dumpp() {
  local key="$1"; shift; [ "$1" = "--" ] && shift
  local f="$dumps/$key.txt"
  if "$java" -jar "$jar" "${scan[@]}" "$@" >"$f" 2>/dev/null && [ -s "$f" ] \
     && ! grep -qE 'Connector not found|Unknown preset' "$f"; then :; else rm -f "$f"; fi
}

echo "==> capturing --help-* output from $jar" >&2

# --- overview / profiles (NO scan-plugins) ---
dump "--help" -- --help --simple
dump "--show-preset=pg-pg-local" -- --show-preset=pg-pg-local
dump "--show-profile=pg-pg" -- --show-profile=pg-pg

# --- ADRs (NO scan) ---
for f in config delivery mapping ordering reprocessing rpo-rto transactions \
         initial-load; do
  dump "--help-$f" -- "--help-$f"
done

# --- worker/connector param help + transforms (WITH scan-plugins, rendered as markdown).
# These support --format=markdown; the flag is added to the RUN args only — the sandbox
# key stays "--help-<f>" so the user types the real command. isMarkdown() then renders it.
for f in worker-params transforms \
         pg-source-params tnt-source-params tnt-sink-params \
         tqe-source-params tqe-sink-params kafka-source-params kafka-sink-params \
         jdbc-sink-params es-sink-params mock-source-params mock-sink-params \
         ingestor-sink-params clickhouse-sink-params mongodb-source-params \
         oracle-source-params sqlserver-source-params; do
  dumpp "--help-$f" -- "--help-$f" --format=markdown
done

# --- preset runbooks: full + --simple, bare + -helm (NO scan) ---
for p in pg-pg-docker pg-pg-local pg-tqe-docker pg-tqe-local tqe-pg-docker tqe-pg-local; do
  for v in "--help-$p" "--help-$p-helm"; do
    dump "$v"          -- "$v"
    dump "$v --simple" -- "$v" --simple
  done
done

# --list-profiles == --help output; alias it so the sandbox recognises it
cp "$dumps/--help.txt" "$dumps/--list-profiles.txt"

echo "==> assembling JSON (commands / tutorials / snippets)" >&2

# commands.json: every dump file → { "<key>": "<output>" }
"$py" - "$dumps" "$tmp/commands.json" <<'PY'
import json, os, sys, glob
dumps, out = sys.argv[1], sys.argv[2]
data = {}
for f in sorted(glob.glob(os.path.join(dumps, "*.txt"))):
    key = os.path.basename(f)[:-4]  # strip .txt; keys already carry the real flag incl. " --simple"
    data[key] = open(f, encoding="utf-8").read().rstrip("\n")
json.dump(data, open(out, "w", encoding="utf-8"), ensure_ascii=False)
print(f"  commands: {len(data)}", file=sys.stderr)
PY

"$py" "$here/build_tutorials.py" "$dumps" "$tmp/tutorials.json"
"$py" "$here/build_snippets.py" "$dumps" "$tmp/snippets.json"

echo "==> baking $outhtml" >&2
"$py" "$here/gen_html.py" "$tmp/commands.json" "$tmp/tutorials.json" "$outhtml" "$tmp/snippets.json"

echo "done: $outhtml" >&2
