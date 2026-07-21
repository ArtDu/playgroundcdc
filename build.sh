#!/usr/bin/env bash
# Dump every --help-* output of the CDC worker jar and bake it into ONE
# self-contained cdc-help.html — opens by double-click (file://), no server,
# no jar/docker needed by whoever you hand it to. Also works on GH Pages as-is.
#
# Usage:
#   JAVA_HOME=/path/to/jdk21 ./build.sh [path/to/cdc-worker.jar]
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
jar="${1:-$here/../target/cdc-worker-1.0.0-SNAPSHOT.jar}"
java="${JAVA_HOME:+$JAVA_HOME/bin/}java"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
outhtml="$here/cdc-help.html"

[ -f "$jar" ] || { echo "jar not found: $jar (build with 'make install-jar')" >&2; exit 1; }

# The plugin scanner looks for connectors in ./plugins or /libs/connect relative
# to CWD; since we run from an arbitrary dir, point it at an absolute path so
# connector --help-*-params and the overview connector table resolve. Override
# with PLUGINS_DIR=... (e.g. for a full-connector build).
plugins="${PLUGINS_DIR:-$here/../../plugins}"
scan=()
if [ -d "$plugins" ]; then
  scan=(--scan-plugins="$(cd "$plugins" && pwd)")
else
  echo "warning: plugins dir not found at $plugins — connector params will be skipped" >&2
fi

# run <slug> <title> <group> -- <jar args...>
# Dumps to $tmp/<slug>.md, records it for embedding. Skips empty/failed runs
# (e.g. a connector whose plugin isn't installed).
# Set FENCE=<lang> before calling to wrap plain (non-markdown) output in a
# ```<lang> code block so marked renders it verbatim instead of as prose.
declare -a slugs titles groups
run() {
  local slug="$1" title="$2" group="$3"; shift 3; [ "$1" = "--" ] && shift
  local f="$tmp/$slug.md"
  if "$java" -jar "$jar" "$@" >"$f" 2>/dev/null && [ -s "$f" ]; then
    # Strip a leading YAML frontmatter block (ADRs start with ---\n...\n---).
    if [ "$(head -1 "$f")" = "---" ]; then
      awk 'NR==1{next} f{print;next} /^---$/{f=1}' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
    fi
    # Fix markdown tables whose cells contain literal newlines (see fix-tables.py).
    # Skipped for fenced (raw) runbook output.
    if [ -z "${FENCE:-}" ]; then
      python3 "$here/fix-tables.py" < "$f" > "$f.tmp" && mv "$f.tmp" "$f"
    fi
    if [ -n "${FENCE:-}" ]; then
      { printf '```%s\n' "$FENCE"; cat "$f"; printf '\n```\n'; } > "$f.tmp"
      mv "$f.tmp" "$f"
    fi
    slugs+=("$slug"); titles+=("$title"); groups+=("$group")
    echo "  ok   $slug"
  else
    rm -f "$f"; echo "  skip $slug (empty / plugin missing)"
  fi
}

echo "Dumping help from $jar"

run overview            "Overview"                    "Overview"    -- --help

run worker-params       "Worker parameters"           "Parameters"  -- --help-worker-params --format=markdown
for a in pg-source oracle-source mongodb-source sqlserver-source kafka-source \
         tnt-source tqe-source tqe-v2-source mock-source \
         jdbc-sink es-sink clickhouse-sink ingestor-sink kafka-sink \
         tnt-sink tqe-sink tqe-v2-sink mock-sink; do
  run "$a-params" "$a" "Parameters" -- "--help-$a-params" --format=markdown "${scan[@]}"
done
run transforms          "Transforms (SMT)"            "Parameters"  -- --help-transforms --format=markdown "${scan[@]}"

run help-config         "Config loading order"        "Concepts"    -- --help-config
run help-transactions   "Transaction semantics"       "Concepts"    -- --help-transactions
run help-delivery       "Delivery guarantees"         "Concepts"    -- --help-delivery
run help-mapping        "Type mapping"                "Concepts"    -- --help-mapping
run help-initial-load   "Initial load & streaming"    "Concepts"    -- --help-initial-load
run help-reprocessing   "Reprocessing / replay"       "Concepts"    -- --help-reprocessing
run help-rpo-rto        "RPO / RTO"                    "Concepts"    -- --help-rpo-rto
run help-ordering       "Event ordering"              "Concepts"    -- --help-ordering

for p in pg-pg-docker pg-pg-local pg-tqe-docker pg-tqe-local tqe-pg-docker tqe-pg-local; do
  FENCE=bash run "runbook-$p" "$p" "Runbooks (docker)" -- "--help-$p"
done
for p in pg-pg pg-tqe tqe-pg; do
  FENCE=bash run "runbook-$p-helm" "$p-helm" "Runbooks (helm)" -- "--help-$p-helm"
done

# Build the embedded JSON payload ({slug,title,group,md}) with jq -Rs so the
# markdown is safely JSON-escaped, then splice it into the template.
docs="$tmp/docs.json"
{
  printf '['
  for i in "${!slugs[@]}"; do
    [ "$i" -gt 0 ] && printf ','
    printf '{"slug":%s,"title":%s,"group":%s,"md":' \
      "$(jq -Rn --arg s "${slugs[$i]}" '$s')" \
      "$(jq -Rn --arg s "${titles[$i]}" '$s')" \
      "$(jq -Rn --arg s "${groups[$i]}" '$s')"
    jq -Rs '.' < "$tmp/${slugs[$i]}.md"
    printf '}'
  done
  printf ']'
} > "$docs"

# Splice payload into the template at the __DOCS__ marker.
python3 - "$here/template.html" "$docs" "$outhtml" <<'PY'
import sys
tpl, docs, out = sys.argv[1], sys.argv[2], sys.argv[3]
html = open(tpl, encoding="utf-8").read()
payload = open(docs, encoding="utf-8").read()
open(out, "w", encoding="utf-8").write(html.replace("/*__DOCS__*/[]", payload))
PY

echo "Done: ${#slugs[@]} pages baked into $outhtml"
echo "Double-click cdc-help.html — no server needed. (Also publishable to GH Pages.)"
