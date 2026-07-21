import sys, re, json

def parse(text):
    lines = text.split("\n")
    steps = []
    pending = []
    i, n = 0, len(lines)
    def heredocs(line):
        return re.findall(r"<<-?\s*'?([A-Za-z_][A-Za-z0-9_]*)'?", line)
    while i < n:
        raw = lines[i]; s = raw.strip()
        if s == "":
            i += 1; continue
        if s.startswith("#"):
            pending.append(s.lstrip("#").strip()); i += 1; continue
        cmd_lines = [raw]
        open_hd = heredocs(raw)
        cont = raw.rstrip().endswith("\\")
        i += 1
        while i < n and (cont or open_hd):
            l = lines[i]; cmd_lines.append(l)
            if open_hd:
                if l.strip() == open_hd[0]:
                    open_hd.pop(0)
            else:
                open_hd = heredocs(l); cont = l.rstrip().endswith("\\")
            i += 1
        steps.append({"note": "\n".join(pending), "cmd": "\n".join(cmd_lines)})
        pending = []
    return steps

if __name__ == "__main__":
    text = open(sys.argv[1], encoding="utf-8").read()
    steps = parse(text)
    print(f"шагов: {len(steps)}", file=sys.stderr)
    json.dump(steps, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False)
