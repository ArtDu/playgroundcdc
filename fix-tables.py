#!/usr/bin/env python3
"""Fix markdown tables whose cells contain literal newlines.

Some connector --help-*-params dumps put multi-line descriptions inside a table
cell: the row starts with `| ... | No | first line`, continues on following
physical lines (indented, flush-left, or blank), and the cell is closed by a
lone ` |` terminator line. marked.js ends the table at the first non-`|` line
and renders the rest as prose, wrecking the layout.

Rule: a table row that does NOT already end in `|` is an unclosed cell. Buffer
following lines; if a lone-`|` terminator appears before the next `|`-row, they
were spillover → fold them into the row (newlines → spaces). If a real `|`-row
or a flush-left markdown line appears first, the table genuinely ended → emit
the buffer verbatim (so real sections like overview's `## Presets` survive).

Reads stdin, writes stdout. Idempotent on already-clean tables.
"""
import re
import sys

ROW = re.compile(r"^\s*\|")
TERM = re.compile(r"^\s*\|\s*$")          # lone "|" — cell terminator
ENDS = re.compile(r"\|\s*$")               # row already closed with trailing |


def dedupe_connector_blocks(lines: list[str]) -> list[str]:
    """Drop duplicate `## io.<class>` connector blocks.

    Some connectors (kafka, tqe, tqe-v2) live in both plugins/source and
    plugins/sink, so --scan-plugins finds the same class twice and prints two
    near-identical blocks (differing only in a random version line). Keep the
    first block per class heading; skip any later block with the same heading.
    """
    out = []
    seen = set()
    skipping = False
    for line in lines:
        if line.startswith("## "):
            if line in seen:
                skipping = True
                continue
            seen.add(line)
            skipping = False
        if not skipping:
            out.append(line)
    return out


def main() -> None:
    lines = sys.stdin.read().splitlines()
    lines = dedupe_connector_blocks(lines)
    out = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if ROW.match(line) and not TERM.match(line) and not ENDS.match(line):
            # Unclosed row: look ahead for a terminator before the next real row.
            j = i + 1
            buf = []
            joined = None
            while j < n:
                nxt = lines[j]
                if TERM.match(nxt):
                    joined = line + " " + " ".join(s.strip() for s in buf if s.strip())
                    j += 1  # consume the terminator
                    break
                if ROW.match(nxt):
                    break  # next table row — this row simply had no trailing |
                buf.append(nxt)
                j += 1
            if joined is not None:
                out.append(joined.rstrip())
                i = j
                continue
        out.append(line)
        i += 1
    sys.stdout.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
