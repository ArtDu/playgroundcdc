import re, json, os, glob, sys

# build_snippets.py <dumps-dir> <out-snippets.json>
#   растаскивает полные docker/local runbook'и на секции по ролям (source/sink/tqe/…)
#   — из них wizard показывает "как поднять источник/приёмник".
ALL = sys.argv[1]
OUTFILE = sys.argv[2]

def sections(text):
    """Режем runbook на секции по '# --- N. Заголовок ---'. Возвращаем [(title, body)]."""
    lines=text.split("\n")
    secs=[]; cur_title=None; cur=[]
    for l in lines:
        m=re.match(r'^# --- \d+\.\s*(.*?)\s*---\s*$', l)
        if m:
            if cur_title is not None: secs.append((cur_title,"\n".join(cur).strip("\n")))
            cur_title=m.group(1); cur=[]
        else:
            if cur_title is not None: cur.append(l)
    if cur_title is not None: secs.append((cur_title,"\n".join(cur).strip("\n")))
    return secs

def classify(title):
    t=title.lower()
    if "monitoring" in t: return "monitoring"
    if "network" in t: return "network"
    if "tqe" in t and ("cluster" in t or "storage" in t): return "tqe"
    if "source postgres" in t: return "source_pg"
    if ("target postgres" in t) or ("sink postgres" in t): return "sink_pg"
    if "cdc worker" in t: return "worker"
    if "create the source table" in t or "insert sample" in t: return "seed"
    if "verify" in t: return "verify"
    if "load generator" in t: return "loadgen"
    if "known limitation" in t: return "note"
    return "other"

# собираем: snippets[preset][role] = {title, body}
snippets={}
for path in glob.glob(os.path.join(ALL,"--help-*.txt")):
    base=os.path.basename(path)[len("--help-"):-4]
    if "-helm" in base or " " in base: continue  # только чистые docker/local runbook'и
    if base not in ("pg-pg-docker","pg-pg-local","pg-tqe-docker","pg-tqe-local","tqe-pg-docker","tqe-pg-local"): continue
    text=open(path,encoding="utf-8").read()
    d={}
    for title,body in sections(text):
        role=classify(title)
        if not body: continue
        # роль worker может встречаться раз; source/sink — раз; кладём первый непустой
        if role not in d: d[role]={"title":title,"body":body}
    snippets[base]=d

json.dump(snippets, open(OUTFILE,"w",encoding="utf-8"), ensure_ascii=False)
for p,d in snippets.items():
    print(f"  snippets {p}: {list(d.keys())}", file=sys.stderr)
