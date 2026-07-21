import re, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_runbook import parse

# build_tutorials.py <dumps-dir> <out-tutorials.json>
#   <dumps-dir> — каталог с дампами вида "--help-<preset>.txt" (полные runbook'и)
DUMPS = sys.argv[1]
OUTFILE = sys.argv[2]

DIM = "\x1b[38;5;250m"  # читаемый серый (не 90m, который тонет на тёмном фоне)
R = "\x1b[0m"

def fake_out(cmd):
    """Правдоподобный фейк-вывод по типу команды. ponytail: эвристика по первому слову/паттерну."""
    first = cmd.strip().split("\n")[0]
    low = first.lower()
    if "docker network create" in low:
        return "3f8a1c9e5b2d4a6f8e0c1b3d5a7f9e2c4b6d8a0f1e3c5b7d9a1f3e5c7b9d1a3f"
    if "docker run -d" in low:
        m = re.search(r"--name (\S+)", first)
        name = m.group(1) if m else "container"
        return ("Unable to find image locally\nlatest: Pulling from library ... done\n"
                "a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456\n"
                f"{DIM}# запущен контейнер {name}{R}")
    if "docker run" in low:  # foreground (worker)
        return (f"{DIM}# воркер стартует в foreground, логи ниже (Ctrl-C для остановки){R}\n"
                "  .   ____          _            __ _ _\n"
                " /\\\\ / ___'_ __ _ _(_)_ __  __ _ \\ \\ \\ \\\n"
                "( ( )\\___ | '_ | '_| | '_ \\/ _` | \\ \\ \\ \\\n"
                "INFO  Started CDCWorkerApplication ... Tomcat started on port 8000\n"
                "INFO  CDC worker 'pg-to-pg-worker' running — source→sink connected")
    if low.startswith("mkdir"):
        return ""  # mkdir тихий
    if low.startswith("cat >") or low.startswith("cat >>"):
        m = re.search(r"cat >+\s*(\S+)", first)
        f = m.group(1) if m else "file"
        return f"{DIM}# записан файл {f}{R}"
    if "psql" in low:
        body = cmd
        out = []
        for kw, rep in [("CREATE TABLE","CREATE TABLE"),("CREATE INDEX","CREATE INDEX"),
                        ("ALTER TABLE","ALTER TABLE"),("CREATE PUBLICATION","CREATE PUBLICATION"),
                        ("DROP TABLE","DROP TABLE")]:
            out += [rep]*len(re.findall(kw, body))
        n_ins = len(re.findall(r"\bINSERT\b", body))
        out += ["INSERT 0 1"]*n_ins
        n_sel = len(re.findall(r"\bSELECT\b", body))
        if n_sel:
            out.append(f"{DIM}# (строки результата SELECT){R}")
        return "\n".join(out) if out else f"{DIM}# psql выполнен{R}"
    if "curl" in low:
        return '{"status":"UP"}' if "actuator" in low or "health" in low else f"{DIM}# HTTP-ответ{R}"
    if low.startswith("helm"):
        return "NAME: cdc-worker\nSTATUS: deployed\nREVISION: 1"
    if low.startswith("kubectl"):
        return f"{DIM}# применено к кластеру{R}"
    if "|| true" in cmd:
        return ""
    return f"{DIM}# команда выполнена (симуляция){R}"

presets = ["pg-pg-docker","pg-pg-local","pg-tqe-docker","pg-tqe-local","tqe-pg-docker","tqe-pg-local"]
tutorials = {}
for p in presets:
    path = os.path.join(DUMPS, f"--help-{p}.txt")
    if not os.path.exists(path):
        continue
    steps = parse(open(path, encoding="utf-8").read())
    tut = [{"note": st["note"], "cmd": st["cmd"], "out": fake_out(st["cmd"])} for st in steps]
    tutorials[p] = tut
    print(f"  tutorial {p}: {len(tut)} шагов", file=sys.stderr)

json.dump(tutorials, open(OUTFILE, "w", encoding="utf-8"), ensure_ascii=False)
