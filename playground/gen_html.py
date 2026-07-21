import json,sys
cmds=json.load(open(sys.argv[1],encoding="utf-8"))
tuts=json.load(open(sys.argv[2],encoding="utf-8"))
snips=json.load(open(sys.argv[4],encoding="utf-8")) if len(sys.argv)>4 else {}
CMDS=json.dumps(cmds,ensure_ascii=False)
TUTS=json.dumps(tuts,ensure_ascii=False)
SNIPS=json.dumps(snips,ensure_ascii=False)
html=r'''<!doctype html>
<html lang="ru"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CDC Worker — песочница команд</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0/css/xterm.css">
<style>
  html,body{margin:0;height:100%;background:#0b0e14;color:#c9d1d9;font-family:system-ui,sans-serif}
  header{padding:10px 16px;border-bottom:1px solid #21262d}
  header b{color:#58a6ff} header span{color:#adbac7;font-size:13px}
  #term{position:absolute;top:52px;left:0;right:0;bottom:0;padding:8px}
</style></head><body>
<header><b>CDC Worker</b> <span>— песочница (симуляция). <code>help</code> — команды · <code>tutorial</code> — пошаговый разбор · Tab — автодополнение.</span></header>
<div id="term"></div>
<script src="https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0/lib/xterm.js"></script>
<script src="https://cdn.jsdelivr.net/npm/@xterm/addon-fit@0.10.0/lib/addon-fit.js"></script>
<script>
const CMDS = __CMDS__;
const TUTS = __TUTS__;
const SNIPS = __SNIPS__;
const PROMPT = "\x1b[36mjava -jar cdc-worker.jar\x1b[0m ";
const SH = "\x1b[32m$\x1b[0m ";
// цвета: DIM — читаемый приглушённый (не 90m), HINT — подсказки, CMD — ожидаемая команда
const DIM="\x1b[38;5;250m", HINT="\x1b[38;5;180m", CMDCOL="\x1b[38;5;117m", R="\x1b[0m";
const term = new Terminal({fontSize:14,cursorBlink:true,theme:{
  background:"#0b0e14", foreground:"#d7dde3",
  brightBlack:"#9aa4af"  // если где-то остался 90m — тоже читаемый
}});
const fit = new FitAddon.FitAddon(); term.loadAddon(fit);
term.open(document.getElementById("term")); fit.fit();
addEventListener("resize",()=>fit.fit());
const wr=t=>term.write(t.replace(/\n/g,"\r\n"));
const keys = Object.keys(CMDS);
const tutNames = Object.keys(TUTS);

// ADR-команды выдают markdown (заголовки, таблицы, code-fence) — их рендерим красиво.
// Runbook'и (docker/helm) НЕ markdown: там # это shell-комментарии, рендерить нельзя.
const MD_CMDS = new Set(["--help-config","--help-delivery","--help-mapping","--help-ordering",
  "--help-reprocessing","--help-rpo-rto","--help-transactions","--help-initial-load"]);

// Мини-рендер markdown -> ANSI для xterm (заголовки, code, таблицы, списки, bold, frontmatter).
function mdRender(src){
  const B="\x1b[1m", CY="\x1b[38;5;117m", GR="\x1b[38;5;108m", GRAY="\x1b[38;5;245m", RS="\x1b[0m";
  const lines=src.split("\n"), out=[]; let inFence=false, fenceBuf=[];
  const inline=s=>s
    .replace(/`([^`]+)`/g, CY+"$1"+RS)               // `код`
    .replace(/\*\*([^*]+)\*\*/g, B+"$1"+RS)          // **жирный**
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");        // [текст](ссылка) -> текст
  // frontmatter --- ... --- в начале: свернём в одну приглушённую строку
  let i=0;
  if(lines[0]==="---"){ let j=1; while(j<lines.length&&lines[j]!=="---") j++;
    const meta=lines.slice(1,j).join(", "); out.push(GRAY+"("+meta+")"+RS); i=j+1; }
  for(; i<lines.length; i++){
    let l=lines[i];
    if(l.startsWith("```")){ if(!inFence){inFence=true;fenceBuf=[];} else {
        inFence=false; out.push(fenceBuf.map(x=>GR+"  │ "+x+RS).join("\r\n")); } continue; }
    if(inFence){ fenceBuf.push(l); continue; }
    let m;
    if(m=l.match(/^(#{1,4})\s+(.*)$/)){ const t=inline(m[2]);
      out.push(""+B+(m[1].length<=2?CY:"")+t+RS); continue; }
    if(l.match(/^\|.*\|/)){                              // строка таблицы
      if(l.match(/^\|[\s:|-]+\|?\s*$/)){ continue; }     // разделитель |---|---| пропускаем
      const cells=l.split("|").slice(1,-1).map(c=>inline(c.trim()));
      out.push("  "+cells.join(GRAY+" · "+RS)); continue; }
    if(m=l.match(/^(\s*)[-*]\s+(.*)$/)){ out.push(m[1]+CY+"• "+RS+inline(m[2])); continue; }
    if(m=l.match(/^(\s*)>\s?(.*)$/)){ out.push(GRAY+"  ▎ "+inline(m[2])+RS); continue; }
    out.push(inline(l));
  }
  return out.join("\r\n");
}
let line="", hist=[], hi=0;
let tut=null;
let wiz=null; // wizard-состояние: {step, from, to, env, srcUp, sinkUp}

function prompt(){ if(tut) showStep(); else if(wiz||cfg) { term.write("\r\n"+SH);} else { term.write("\r\n"+PROMPT); } }

// ===== Wizard: ведёт незнакомого с продуктом пользователя от "что перелить" до запуска =====
// Валидные потоки (что реально умеет продукт): pg->pg, pg->tqe, tqe->pg. tqe->tqe нет.
const FLOWS = { "pg|pg":"pg-pg", "pg|tqe":"pg-tqe", "tqe|pg":"tqe-pg" };
const ELABEL = {pg:"PostgreSQL", tqe:"очередь TQE"};
const ENVLABEL = {docker:"в Docker", local:"на своей машине (java -jar)", k8s:"в Kubernetes (Helm)"};

function parseEndpoint(inp){ const s=inp.toLowerCase();
  if(s==="1"||/\bp(ost)?g|postgres|бд|база/.test(s)) return "pg";
  if(s==="2"||/tqe|очеред|queue|tarantool|тарантул/.test(s)) return "tqe";
  return null; }
function parseEnv(inp){ const s=inp.toLowerCase();
  if(s==="1"||/doc?ker|докер|контейнер/.test(s)) return "docker";
  if(s==="2"||/local|локал|jar|java|машин/.test(s)) return "local";
  if(s==="3"||/k8s|kuber|kube|куб|helm|хелм/.test(s)) return "k8s";
  return null; }
function parseYN(inp){ const s=inp.toLowerCase().trim();
  if(s==="1"||/^(да|д|yes|y|подн|есть|готов)/.test(s)) return true;
  if(s==="2"||/^(нет|н|no|n|не )/.test(s)) return false;
  return null; }

function askFrom(){ wr("\r\n\x1b[1mОткуда берём данные?\x1b[0m\r\n  "+CMDCOL+"1)"+R+" PostgreSQL  "+DIM+"(обычная база)"+R+"\r\n  "+CMDCOL+"2)"+R+" Очередь Tarantool (TQE)  "+DIM+"(данные уже лежат в очереди)"+R+"\r\n"+HINT+"Ответьте цифрой или словом (pg / очередь). quit — выйти."+R); }
function askTo(){ wr("\r\n\x1b[1mКуда перелить?\x1b[0m\r\n  "+CMDCOL+"1)"+R+" PostgreSQL\r\n  "+CMDCOL+"2)"+R+" Очередь Tarantool (TQE)  "+DIM+"(положить в очередь как буфер)"+R); }
function askEnv(){ wr("\r\n\x1b[1mГде будете запускать перекачку?\x1b[0m\r\n  "+CMDCOL+"1)"+R+" В Docker  "+DIM+"(всё в контейнерах)"+R+"\r\n  "+CMDCOL+"2)"+R+" На своей машине  "+DIM+"(java -jar)"+R+"\r\n  "+CMDCOL+"3)"+R+" В Kubernetes  "+DIM+"(Helm-чарт)"+R); }
function askSrcUp(){ wr("\r\n\x1b[1m"+ELABEL[wiz.from]+"-источник уже поднят и доступен?\x1b[0m\r\n  "+CMDCOL+"1)"+R+" Да, работает  "+CMDCOL+"2)"+R+" Нет, надо поднять"); }
function askSinkUp(){ wr("\r\n\x1b[1m"+ELABEL[wiz.to]+"-приёмник уже поднят?\x1b[0m\r\n  "+CMDCOL+"1)"+R+" Да  "+CMDCOL+"2)"+R+" Нет, надо поднять"); }

function startWiz(){
  wiz={step:"from"};
  wr("\r\n\x1b[1;33m=== Помощник настройки переливки ===\x1b[0m");
  wr("\r\n"+HINT+"Отвечу на несколько вопросов и соберу полный план: что скачать, что поднять, чем запустить."+R+"\r\n");
  askFrom(); term.write("\r\n"+SH);
}
function wizAnswer(input){
  const inp=input.trim();
  if(inp==="quit"||inp==="exit"){ wr("\r\n\x1b[33mВыход из помощника.\x1b[0m"); wiz=null; term.write("\r\n"+PROMPT); return; }
  const bad=(msg,ask)=>{ wr("\r\n\x1b[33m"+msg+"\x1b[0m"); ask(); term.write("\r\n"+SH); };
  switch(wiz.step){
    case "from": { const e=parseEndpoint(inp);
      if(!e) return bad("Не понял. 1, 2 или: pg / очередь.",askFrom);
      wiz.from=e; wiz.step="to"; askTo(); return term.write("\r\n"+SH); }
    case "to": { const e=parseEndpoint(inp);
      if(!e) return bad("Не понял. 1, 2 или: pg / очередь.",askTo);
      const flow=FLOWS[wiz.from+"|"+e];
      if(!flow) return bad("Очередь→очередь продукт напрямую не переливает. Выберите другой приёмник:",askTo);
      wiz.to=e; wiz.flow=flow; wiz.step="env"; askEnv(); return term.write("\r\n"+SH); }
    case "env": { const v=parseEnv(inp);
      if(!v) return bad("Не понял. 1, 2, 3 или: docker / машина / k8s.",askEnv);
      wiz.env=v;
      if(v==="k8s"){ return wizFinishK8s(); }   // для k8s поднятие БД идёт своим helm-планом
      wiz.step="srcUp"; askSrcUp(); return term.write("\r\n"+SH); }
    case "srcUp": { const y=parseYN(inp);
      if(y===null) return bad("Да или нет? (1/2, да/нет)",askSrcUp);
      wiz.srcUp=y; wiz.step="sinkUp"; askSinkUp(); return term.write("\r\n"+SH); }
    case "sinkUp": { const y=parseYN(inp);
      if(y===null) return bad("Да или нет? (1/2, да/нет)",askSinkUp);
      wiz.sinkUp=y; return wizFinish(); }
  }
}

// Преамбула: что скачать из Customer Zone и распаковать — зависит от среды
function bundlePreamble(env){
  const head=DIM+"# 0. Пакет поставки (delivery bundle)"+R+"\r\n"+
    "Скачайте один архив "+CMDCOL+"tarantool-cdc-bundle-*.tar.gz"+R+" из личного кабинета\r\n"+
    "(Tarantool Customer Zone) и распакуйте — внутри уже всё нужное:\r\n"+
    DIM+"  tar xzf tarantool-cdc-bundle-*.tar.gz && cd tarantool-cdc-bundle-*"+R+"\r\n";
  if(env==="docker") return head+
    "Загрузите docker-образ из бандла:\r\n"+
    CMDCOL+"  docker load -i cdc-worker-all-*-docker-image.tar.gz"+R;
  if(env==="local") return head+
    "Для запуска нужны "+CMDCOL+"cdc-worker-*.jar"+R+" и папка "+CMDCOL+"plugins/"+R+" рядом — они уже в бандле.\r\n"+
    DIM+"(java 21 должна быть установлена)"+R;
  if(env==="k8s") return head+
    "Для k8s нужен чарт "+CMDCOL+"helm-chart-cdc/"+R+" из бандла (на него укажет CHART ниже).";
  return head;
}

function snippetFor(role, note){
  const s=SNIPS[wiz.flow+"-"+wiz.env];
  if(!s||!s[role]) return null;
  return DIM+"# "+(note||s[role].title)+R+"\r\n"+CMDCOL+s[role].body+R;
}

function wizFinish(){
  const preset=wiz.flow+"-"+wiz.env;
  const run=CMDS["--help-"+preset+" --simple"]||"(команда не найдена)";
  wr("\r\n\r\n\x1b[1;32m✓ План готов.\x1b[0m Переливка "+ELABEL[wiz.from]+" → "+ELABEL[wiz.to]+" ("+ENVLABEL[wiz.env]+").\r\n");
  wr("\r\n"+bundlePreamble(wiz.env)+"\r\n");
  if(!wiz.srcUp){ const sn=snippetFor(wiz.from==="tqe"?"tqe":"source_pg","Поднять источник ("+ELABEL[wiz.from]+")");
    if(sn) wr("\r\n"+sn+"\r\n"); }
  if(!wiz.sinkUp){ const sn=snippetFor(wiz.to==="tqe"?"tqe":"sink_pg","Поднять приёмник ("+ELABEL[wiz.to]+")");
    if(sn) wr("\r\n"+sn+"\r\n"); }
  if(wiz.srcUp&&wiz.sinkUp){ wr("\r\n"+DIM+"# Источник и приёмник у вас уже есть — сразу запускаем перекачку."+R+"\r\n"); }
  wr("\r\n"+DIM+"# Запуск перекачки (worker):"+R+"\r\n"+CMDCOL+run+R);
  wr("\r\n\r\n"+HINT+"Нужно задать свой адрес БД, логин или другие параметры? "+R+CMDCOL+"config"+R+HINT+" — покажет, что и куда.\r\n"+
     "Показать весь процесс по шагам (с тестовыми данными и проверкой)? "+R+CMDCOL+"tutorial "+preset+R+"\r\n"+
     HINT+"Начать заново — "+R+CMDCOL+"start"+R);
  wiz=null; term.write("\r\n"+PROMPT);
}
function wizFinishK8s(){
  const preset=wiz.flow+"-docker";              // helm-план цепляется к docker-варианту связки
  const helm=CMDS["--help-"+wiz.flow+"-docker-helm --simple"]||CMDS["--help-"+wiz.flow+"-local-helm --simple"]||"(helm-план не найден)";
  wr("\r\n\r\n\x1b[1;32m✓ План готов.\x1b[0m Переливка "+ELABEL[wiz.from]+" → "+ELABEL[wiz.to]+" (в Kubernetes).\r\n");
  wr("\r\n"+bundlePreamble("k8s")+"\r\n");
  wr("\r\n"+DIM+"# Развёртывание в кластер (values + helm install). Источник/приёмник — это адреса ваших\r\n"+
     "# уже поднятых БД/очереди; впишите их в values ниже (SRC_INTERNAL_IP / SINK_INTERNAL_IP):"+R+"\r\n");
  wr(CMDCOL+helm+R);
  wr("\r\n\r\n"+HINT+"Нужно задать свой адрес БД, логин или другие параметры в values? "+R+CMDCOL+"config"+R+HINT+" — покажет, что и куда.\r\n"+
     "Полный k8s-сценарий (Terraform-ВМ для БД, установка образа, проверка) — "+R+CMDCOL+"--help-"+wiz.flow+"-docker-helm"+R+"\r\n"+
     HINT+"Начать заново — "+R+CMDCOL+"start"+R);
  wiz=null; term.write("\r\n"+PROMPT);
}

// ===== Config-помощник: как поменять параметр =====================================
// Учит: (1) как узнать параметр (--help-*-params), (2) КУДА его вписать в 3 средах.
// helm-маппинг выверен по шаблону чарта k8s/helm-chart-cdc/templates/workers.yaml:
// он рендерит application.yaml из values — sources.<n>.common -> source:, sinks.<n>.common
// -> sink:, .Values.offset -> offset:, flow[].throttle -> throttle:. Ключа root.* как
// универсального НЕТ (root — отдельный escape-hatch, объясняем в конце).
let cfg=null;

function toEnv(key){ return key.toUpperCase().replace(/[.\-]/g,"_"); }        // Spring relaxed binding
function yamlNest(key, val, base){                                            // key "a.b.c" -> вложенный YAML
  const parts=key.split("."); let ind=base||0;
  return parts.map((p,i)=>"  ".repeat(ind+i)+p+(i===parts.length-1?": "+val:":")).join("\r\n");
}
// Показывает параметр в схемах ЦЕЛИКОМ — как реально запустить с ним. fullKey — полный Spring-ключ.
// В local И docker работают ОБА способа — CLI-флаг и env-переменная; плюс файл ./config/application.yml.
function localDocker(fullKey,val){
  const env=toEnv(fullKey);
  return "  "+DIM+"• способ 1 — CLI-флаг "+R+CMDCOL+"--"+fullKey+"="+val+R+DIM+" (в конце команды запуска):"+R+"\r\n"+
         "    "+DIM+"local:"+R+"  "+CMDCOL+"java -jar cdc-worker.jar --preset=pg-pg-local --"+fullKey+"="+val+R+"\r\n"+
         "    "+DIM+"docker:"+R+" "+CMDCOL+"docker run --rm --network stand-net cdc-worker-all:<tag> \\\r\n              --preset=pg-pg-docker --"+fullKey+"="+val+R+"\r\n\r\n"+
         "  "+DIM+"• способ 2 — env-переменная "+R+CMDCOL+env+"="+val+R+DIM+" (тот же ключ; удобно для секретов):"+R+"\r\n"+
         "    "+DIM+"local:"+R+"  "+CMDCOL+env+"="+val+" java -jar cdc-worker.jar --preset=pg-pg-local"+R+"\r\n"+
         "    "+DIM+"docker:"+R+" "+CMDCOL+"docker run --rm --network stand-net -e "+env+"="+val+" \\\r\n              cdc-worker-all:<tag> --preset=pg-pg-docker"+R+"\r\n\r\n"+
         "  "+DIM+"• способ 3 — файл "+R+CMDCOL+"./config/application.yml"+R+DIM+" рядом с воркером\r\n"+
         "    (проще, когда параметров много: держите override отдельно от jar). Создаём файл целиком:"+R+"\r\n"+CMDCOL+
         "    mkdir -p config\r\n"+
         "    cat > config/application.yml <<'EOF'\r\n"+
         yamlNest(fullKey,val,2).split("\r\n").map(l=>"    "+l.slice(2)).join("\r\n")+"\r\n"+
         "    EOF"+R+"\r\n"+
         "    "+DIM+"# запуск как обычно — файл из ./config подхватится сам:"+R+"\r\n"+
         "    "+CMDCOL+"java -jar cdc-worker.jar --preset=pg-pg-local"+R+"\r\n"+
         "    "+DIM+"# в docker тот же файл монтируется внутрь: "+R+CMDCOL+"-v $PWD/config:/workspace/config"+R;
}

function cfgIntro(){
  wr("\r\n\x1b[1;33m=== Как поменять параметр CDC Worker ===\x1b[0m\r\n");
  wr("\r\nЛюбой параметр можно переопределить снаружи, не пересобирая jar и не трогая\r\n"+
     "файлы внутри него. "+DIM+"Кто задан позже — тот побеждает:"+R+"\r\n"+
     "  "+DIM+"jar < внешний application.yml < env < CLI (--key=value)."+R+"\r\n");
  wr("\r\n"+DIM+"Для local и docker есть три равноценных способа — все три работают в ОБЕИХ средах:"+R+"\r\n"+
     "  "+CMDCOL+"1. CLI"+R+"   — флаг "+CMDCOL+"--key=value"+R+"  "+DIM+"(быстро для 1–2 параметров)"+R+"\r\n"+
     "  "+CMDCOL+"2. env"+R+"   — переменная "+CMDCOL+"KEY=value"+R+"  "+DIM+"(тот же ключ; удобно для секретов)"+R+"\r\n"+
     "  "+CMDCOL+"3. файл"+R+"  — свой "+CMDCOL+"./config/application.yml"+R+" рядом с воркером  "+DIM+"(лучше всего,\r\n"+
     "            когда параметров много: держите override-файл отдельно от jar).\r\n"+
     "            Воркер сам подхватывает ./config/ и переписывает им дефолты."+R+"\r\n");
  wr("\r\n"+HINT+"Порядок загрузки целиком — "+R+CMDCOL+"--help-config"+R+"\r\n");
}
function cfgMenu(){
  wr("\r\n\x1b[1mЧто нужно?\x1b[0m\r\n"+
     "  "+CMDCOL+"1)"+R+" Узнать, какие параметры вообще есть\r\n"+
     "  "+CMDCOL+"2)"+R+" Поменять параметр "+DIM+"коннектора"+R+" (адрес, порт, логин источника/приёмника…)\r\n"+
     "  "+CMDCOL+"3)"+R+" Поменять параметр "+DIM+"воркера"+R+" (offset, throttle, retry…)\r\n"+
     "  "+CMDCOL+"4)"+R+" Как воркер берёт настройки: "+DIM+"application.yaml → профили → пресет"+R+"\r\n"+
     "  "+CMDCOL+"5)"+R+" Короткие псевдонимы ("+DIM+"pg.source.host…"+R+") и ключ "+DIM+"root"+R+" в Kubernetes\r\n"+
     HINT+"quit — выйти."+R);
}
function startCfg(){ cfg={step:"menu"}; cfgIntro(); cfgMenu(); term.write("\r\n"+SH); }

function cfgListParams(){
  const conn=keys.filter(k=>k.endsWith("-params")&&k!=="--help-worker-params");
  wr("\r\n\x1b[1mПараметры воркера\x1b[0m (offset, throttle, retry, таймауты) — сгруппированы по секциям:\r\n"+
     "  "+CMDCOL+"java -jar cdc-worker.jar --help-worker-params"+R+"\r\n");
  wr("\r\n\x1b[1mПараметры коннекторов\x1b[0m (свои у каждого source/sink — host, port, …). Вызов:\r\n"+
     "  "+CMDCOL+"java -jar cdc-worker.jar <любая из команд ниже>"+R+"\r\n  "+conn.map(k=>CMDCOL+k+R).join("\r\n  "));
  wr("\r\n\r\n"+HINT+"Наберите любую из них (без java -jar) прямо здесь, чтобы увидеть полный список\r\n"+
     "с дефолтами. Куда вписать найденный параметр — "+R+CMDCOL+"config"+R+HINT+" → 2 (коннектор) или 3 (воркер)."+R);
  cfg=null; term.write("\r\n"+PROMPT);
}

// Коннекторный параметр: имя из --help-<c>-params, воркер ждёт с префиксом source/sink.connector.
function cfgConnector(){
  wr("\r\n\x1b[1;36m── Параметр коннектора (адрес, порт, логин источника/приёмника) ──\x1b[0m\r\n");
  wr("\r\nУ каждого коннектора (PostgreSQL, TQE, Kafka…) свой набор параметров. Меняем в 3 шага.\r\n"+
     DIM+"Для примера настроим адрес PostgreSQL-источника — то, что нужно почти всегда."+R+"\r\n");

  wr("\r\n\x1b[1mШаг 1. Узнать имя параметра.\x1b[0m\r\n"+
     "Вызовите справку нужного коннектора, например PostgreSQL-источник:\r\n"+
     "  "+CMDCOL+"java -jar cdc-worker.jar --help-pg-source-params"+R+"\r\n\r\n"+
     "Вывод — параметры коннектора "+DIM+"(имя : тип = значение по умолчанию, сокращённо)"+R+":\r\n\r\n"+
     "  \x1b[1m[Postgres]\x1b[0m\r\n"+
     "    "+CMDCOL+"database.hostname"+R+DIM+" : string"+R+"\r\n"+
     "        Адрес (хост или IP) сервера базы-источника.\r\n"+
     "    "+CMDCOL+"database.port"+R+DIM+" : int = 5432"+R+"\r\n"+
     "        Порт базы.\r\n"+
     "    "+CMDCOL+"database.dbname"+R+DIM+" : string"+R+"\r\n"+
     "        Имя базы данных.\r\n\r\n"+
     HINT+"Возьмём "+R+CMDCOL+"database.hostname"+R+HINT+" — зададим адрес источника."+R+"\r\n");

  wr("\r\n\x1b[1mШаг 2. Добавить приставку.\x1b[0m\r\n"+
     "Воркер держит сразу два коннектора — источник и приёмник, поэтому к имени параметра\r\n"+
     "спереди дописывают, чей он:\r\n"+
     "  • параметр источника  → "+CMDCOL+"source.connector."+R+DIM+" + имя"+R+"\r\n"+
     "  • параметр приёмника  → "+CMDCOL+"sink.connector."+R+DIM+" + имя"+R+"\r\n"+
     "Полное имя для нашего примера (источник):\r\n"+
     "  "+CMDCOL+"source.connector.database.hostname"+R+"\r\n");

  wr("\r\n\x1b[1mШаг 3. Задать значение\x1b[0m (адрес "+CMDCOL+"pg-1.local"+R+"). Выберите свою среду:\r\n\r\n");
  wr(localDocker("source.connector.database.hostname","pg-1.local")+"\r\n\r\n");

  wr("  "+DIM+"• Kubernetes — в values.yaml под вашим именем источника. Важное отличие: приставку\r\n"+
     "    "+R+CMDCOL+"source.connector."+R+DIM+" НЕ пишем — её заменяют ключи "+R+CMDCOL+"sources: → <имя> → common: → connector:"+R+DIM+".\r\n"+
     "    Чарт сам соберёт из этого нужный source.connector.* в настройках воркера:"+R+"\r\n"+
     helmFile("sources:\r\n  my-pg:                  # любое ваше имя источника\r\n    common:\r\n      connector:\r\n        database:\r\n          hostname: pg-1.local")+"\r\n");

  wr("\r\n"+HINT+"Тот же приём для любого параметра любого коннектора — см. список в "+R+CMDCOL+"config"+R+HINT+" → 1. Назад в меню — "+R+CMDCOL+"config"+R);
  cfg=null; term.write("\r\n"+PROMPT);
}

// Воркерный параметр: место в helm зависит от секции (offset/throttle/source|sink/прочее).
function cfgWorker(){
  wr("\r\n\x1b[1;36m── Параметр воркера (offset, throttle, retry, таймауты) ──\x1b[0m\r\n");
  wr("\r\n\x1b[1mШаг 1. Посмотреть, какие параметры есть.\x1b[0m Вызовите:\r\n"+
     "  "+CMDCOL+"java -jar cdc-worker.jar --help-worker-params"+R+"\r\n\r\n"+
     "Вывод сгруппирован по секциям, каждый параметр — "+DIM+"ключ : тип = дефолт"+R+" и описание ниже "+DIM+"(сокращённо)"+R+":\r\n\r\n"+
     "  \x1b[1m[offset]\x1b[0m\r\n"+
     "    "+CMDCOL+"offset.storage"+R+DIM+" : list"+R+"\r\n"+
     "        Где хранить offset-ы: file / kafka / tqe.\r\n"+
     "    "+CMDCOL+"offset.flush.interval.ms"+R+DIM+" : long = 5000"+R+"\r\n"+
     "        Интервал периодического сохранения offset-ов, мс.\r\n"+
     "  \x1b[1m[throttle]\x1b[0m\r\n"+
     "    "+CMDCOL+"throttle.throttler.max.rps"+R+DIM+" : int = -1"+R+"\r\n"+
     "        Потолок скорости, записей/сек. -1 — без ограничения.\r\n"+
     "  \x1b[1m[sink]\x1b[0m\r\n"+
     "    "+CMDCOL+"sink.retry.count"+R+DIM+" : int = 5"+R+"\r\n"+
     "        Число повторов при ошибке записи в sink.\r\n");
  wr("\r\n\x1b[1mШаг 2. Вписать значение.\x1b[0m Имя берётся как есть — префикс "+DIM+"(source.connector./sink.connector.)"+R+"\r\n"+
     "тут НЕ нужен, он только у параметров коннекторов. "+DIM+"В local/docker место всегда одно;\r\n"+
     "в helm зависит от секции (чарт раскладывает секции по разным местам values.yaml)."+R+"\r\n");

  wr("\r\n\x1b[1m① offset.storage\x1b[0m "+DIM+"(секция [offset])"+R+" — где хранить offset-ы:\r\n");
  wr(localDocker("offset.storage","file")+"\r\n\r\n");
  wr("  "+DIM+"• helm — секция "+R+CMDCOL+"offset:"+R+DIM+" верхнего уровня values.yaml (общая на воркер):"+R+"\r\n"+
     helmFile("offset:\r\n  storage: file")+"\r\n");

  wr("\r\n\x1b[1m② throttle.throttler.max.rps\x1b[0m "+DIM+"(секция [throttle])"+R+" — потолок скорости, записей/сек:\r\n");
  wr(localDocker("throttle.throttler.max.rps","1000")+"\r\n\r\n");
  wr("  "+DIM+"• helm — внутри конкретного пайплайна "+R+CMDCOL+"flow:"+R+DIM+" (у каждого потока свой throttle):"+R+"\r\n"+
     helmFile("flow:\r\n  - source: my-pg\r\n    sink: my-pg\r\n    throttle:\r\n      throttler:\r\n        max.rps: 1000")+"\r\n");

  wr("\r\n\x1b[1m③ sink.retry.count\x1b[0m "+DIM+"(секция [sink])"+R+" — сколько раз повторять запись в приёмник:\r\n");
  wr(localDocker("sink.retry.count","10")+"\r\n\r\n");
  wr("  "+DIM+"• helm — внутри логического приёмника "+R+CMDCOL+"sinks.<имя>.common"+R+DIM+", ключ без префикса sink.:"+R+"\r\n"+
     helmFile("sinks:\r\n  my-pg:\r\n    common:\r\n      retry:\r\n        count: 10")+"\r\n");

  wr("\r\n"+HINT+"Правило helm: [offset] → offset:, [throttle] → flow[].throttle, [source]/[sink] →\r\n"+
     "sources|sinks.<имя>.common. В local/docker всегда просто полный ключ. Меню — "+R+CMDCOL+"config"+R);
  cfg=null; term.write("\r\n"+PROMPT);
}
// helm-values как воспроизводимый рецепт: создать values.yaml целиком через cat, затем apply.
// yamlBody — строки YAML (с отступами от начала, \r\n между), напр. "offset:\r\n  storage: file".
function helmFile(yamlBody){
  const body=yamlBody.split("\r\n").map(l=>"    "+l).join("\r\n");
  return "    "+DIM+"# создаём values.yaml целиком:"+R+"\r\n"+CMDCOL+
         "    cat > values.yaml <<'EOF'\r\n"+body+"\r\n    EOF"+R+"\r\n"+
         "    "+DIM+"# и применяем (chart — из распакованного бандла helm-chart-cdc):"+R+"\r\n"+CMDCOL+
         "    helm upgrade --install cdc ./helm-chart-cdc -f values.yaml"+R;
}

function cfgConcepts(){
  wr("\r\n\x1b[1;36m── Откуда воркер берёт настройки: application.yaml → профили → пресет ──\x1b[0m\r\n");

  wr("\r\n\x1b[1m1. Базовый файл настроек\x1b[0m "+CMDCOL+"application.yaml"+R+"\r\n"+
     "Он уже встроен в воркер и включён всегда. В нём лежат значения по умолчанию —\r\n"+
     "размеры таймаутов, интервалы и прочее. "+DIM+"Но коннекторы (откуда и куда лить) в нём НЕ\r\n"+
     "заданы."+R+" Поэтому если просто запустить голый воркер:\r\n"+
     "  "+CMDCOL+"java -jar cdc-worker.jar"+R+"\r\n"+
     DIM+"…он упадёт с ошибкой «"+R+CMDCOL+"source.connector.class (required)"+R+DIM+"» — не знает, что подключать.\r\n"+
     "Значит воркеру нужно доснабдить настройками. Есть три уровня удобства — разберём по порядку."+R+"\r\n");

  wr("\r\n\x1b[1m2. Профили\x1b[0m — маленькие готовые куски настроек, тоже встроены в воркер\r\n"+
     "(файлы "+DIM+"application-<имя>.yml"+R+"). Каждый решает одну задачу. Например профиль "+CMDCOL+"pg-source"+R+"\r\n"+
     "уже настраивает коннектор к PostgreSQL-источнику с нашими значениями по умолчанию:\r\n"+
     "  "+CMDCOL+"java -jar cdc-worker.jar --show-profile=pg-source"+R+"  "+DIM+"— посмотреть, что внутри"+R+"\r\n"+
     DIM+"    source:\r\n"+
     DIM+"      connector:\r\n"+
     DIM+"        class: io.debezium.connector.postgresql.PostgresConnector\r\n"+
     DIM+"        database:\r\n"+
     DIM+"          hostname: ${pg.source.host:localhost}   # по умолчанию localhost\r\n"+
     DIM+"          port:     ${pg.source.port:5432}"+R+"\r\n"+
     "Другие профили: "+CMDCOL+"snapshot-initial"+R+" (сначала все текущие данные, потом новые), "+CMDCOL+"offset-tqe"+R+"\r\n"+
     "(хранить позицию в очереди TQE) и т.д. Включить один или несколько:\r\n"+
     "  "+CMDCOL+"java -jar cdc-worker.jar --profile=pg-source,pg-sink,offset-file"+R+"\r\n");

  wr("\r\n\x1b[1m3. Пресет\x1b[0m — чтобы не перечислять профили руками, мы собрали их в один алиас\r\n"+
     "под конкретную связку (поток данных, flow). Указываете одно слово — включаются все\r\n"+
     "нужные профили сразу:\r\n"+
     "  "+CMDCOL+"java -jar cdc-worker.jar --preset=pg-pg-local"+R+"  "+DIM+"— связка PostgreSQL → PostgreSQL"+R+"\r\n"+
     "  "+CMDCOL+"java -jar cdc-worker.jar --show-preset=pg-pg-local"+R+"  "+DIM+"— какие профили он включит"+R+"\r\n");

  wr("\r\n\x1b[1mЧто реально нужно задать для первого запуска\x1b[0m\r\n"+
     "Пресет уже даёт рабочую заготовку. Обычно поверх неё остаётся указать только своё —\r\n"+
     "и то лишь если у вас не "+DIM+"localhost:порт-по-умолчанию"+R+":\r\n"+
     "  • адрес источника и приёмника:  "+CMDCOL+"pg.source.host"+R+", "+CMDCOL+"pg.source.port"+R+", "+CMDCOL+"pg.sink.host"+R+", "+CMDCOL+"pg.sink.port"+R+"\r\n"+
     "  • какие таблицы переливать:      "+CMDCOL+"pg.source.tables"+R+DIM+" (напр. public.users,public.orders)"+R+"\r\n"+
     "Пример полного первого запуска (пресет + свои адреса и таблицы):\r\n"+
     "  "+CMDCOL+"java -jar cdc-worker.jar --preset=pg-pg-local \\\r\n"+
     "    --pg.source.host=pg-1.local --pg.source.port=5432 \\\r\n"+
     "    --pg.sink.host=pg-2.local --pg.sink.port=5432 \\\r\n"+
     "    --pg.source.tables=public.users,public.orders"+R+"\r\n"+
     DIM+"(эти короткие "+R+CMDCOL+"pg.source.*"+R+DIM+" — наши удобные псевдонимы; они и есть те самые\r\n"+
     "значения по умолчанию из профиля, которые вы переопределяете. Полный список параметров\r\n"+
     "коннектора — "+R+CMDCOL+"config"+R+DIM+" → 2. Подробнее про псевдонимы и как их задать в Kubernetes — "+R+CMDCOL+"config"+R+DIM+" → 5.)"+R+"\r\n");

  wr("\r\n\r\n"+HINT+"Назад в меню — "+R+CMDCOL+"config"+R);
  cfg=null; term.write("\r\n"+PROMPT);
}

// Пункт 5: короткие псевдонимы (profile aliases) и ключ root в Kubernetes.
function cfgAliases(){
  wr("\r\n\x1b[1;36m── Короткие псевдонимы и ключ root в Kubernetes ──\x1b[0m\r\n");

  wr("\r\n\x1b[1mЧто такое короткие псевдонимы\x1b[0m\r\n"+
     "В наших профилях параметры коннектора завязаны на удобные короткие имена. Например\r\n"+
     "внутри профиля "+CMDCOL+"pg-source"+R+" стоит:\r\n"+
     DIM+"    hostname: ${pg.source.host:localhost}"+R+"\r\n"+
     "Это значит: «возьми "+CMDCOL+"pg.source.host"+R+", а если не задан — используй "+DIM+"localhost"+R+"».\r\n"+
     "Поэтому вместо длинного "+DIM+"source.connector.database.hostname"+R+" вы пишете короткое\r\n"+
     "  "+CMDCOL+"pg.source.host"+R+" — это и есть псевдоним. Полный список — в профиле ("+CMDCOL+"--show-profile=pg-source"+R+").\r\n");

  wr("\r\n\x1b[1mВ local и docker\x1b[0m псевдоним задаётся как любой параметр — флагом, переменной или файлом:\r\n"+
     "  "+CMDCOL+"java -jar cdc-worker.jar --preset=pg-pg-local --pg.source.host=pg-1.local"+R+"\r\n"+
     "  "+CMDCOL+"PG_SOURCE_HOST=pg-1.local java -jar cdc-worker.jar --preset=pg-pg-local"+R+"\r\n");

  wr("\r\n\x1b[1mВ Kubernetes — тут и нужен ключ "+R+CMDCOL+"root"+R+"\x1b[1m\x1b[0m\r\n"+
     "Псевдоним "+CMDCOL+"pg.source.host"+R+" — это ключ в "+DIM+"корне"+R+" настроек (не внутри "+DIM+"source:"+R+" или "+DIM+"sink:"+R+").\r\n"+
     "Задать его в Kubernetes можно и через "+CMDCOL+"env"+R+", и прямо в values — но получается коряво\r\n"+
     "(значения источника оказываются размазаны по разным местам). Поэтому в чарт добавили ключ\r\n"+
     ""+CMDCOL+"root"+R+": всё, что в него положишь, чарт выносит в "+DIM+"корень"+R+" итоговых настроек воркера —\r\n"+
     "ровно туда, где псевдонимы и ждут. Кладём его рядом с источником:\r\n"+
     helmFile("sources:\r\n  my-pg:\r\n    common:\r\n      connector:\r\n        class: io.debezium.connector.postgresql.PostgresConnector\r\n    root:                       # уедет в корень настроек\r\n      pg:\r\n        source:\r\n          host: pg-1.local\r\n          tables: public.users,public.orders")+"\r\n");

  wr("\r\n"+DIM+"Короче: "+R+CMDCOL+"root"+R+DIM+" нужен только в Kubernetes и только для корневых ключей —\r\n"+
     "коротких псевдонимов "+R+CMDCOL+"pg.source.*"+R+DIM+" и общих настроек воркера ("+R+CMDCOL+"cdc.worker.*"+R+DIM+").\r\n"+
     "Обычные параметры коннектора вписывают без него — как в "+R+CMDCOL+"config"+R+DIM+" → 2."+R);

  wr("\r\n\r\n"+HINT+"Назад в меню — "+R+CMDCOL+"config"+R);
  cfg=null; term.write("\r\n"+PROMPT);
}

function cfgAnswer(input){
  const inp=input.trim().toLowerCase();
  if(inp==="quit"||inp==="exit"){ wr("\r\n\x1b[33mВыход.\x1b[0m"); cfg=null; term.write("\r\n"+PROMPT); return; }
  if(cfg.step==="menu"){
    if(inp==="1"||/парам|есть|список|узна/.test(inp)){ cfgListParams(); return; }
    if(inp==="2"||/коннект|host|port|источ|приём|connector/.test(inp)){ cfgConnector(); return; }
    if(inp==="3"||/воркер|offset|throttle|retry|worker/.test(inp)){ cfgWorker(); return; }
    if(inp==="4"||/пресет|профил|preset|profile|настройк|application/.test(inp)){ cfgConcepts(); return; }
    if(inp==="5"||/псевдоним|алиас|alias|root|kuber|k8s/.test(inp)){ cfgAliases(); return; }
    wr("\r\n\x1b[33mНе понял. 1, 2, 3, 4 или 5.\x1b[0m"); cfgMenu(); term.write("\r\n"+SH); return;
  }
}


function startTut(name){
  if(!TUTS[name]){ wr("\r\n\x1b[31mНет tutorial:\x1b[0m "+name+"\r\nДоступны: "+tutNames.join("  ")); term.write("\r\n"+PROMPT); return; }
  tut={name, steps:TUTS[name], idx:0};
  wr("\r\n\x1b[1;33m=== Tutorial: "+name+" ("+tut.steps.length+" шагов) ===\x1b[0m");
  wr("\r\n"+HINT+"Печатайте команду и Enter — или просто Enter, чтобы выполнить показанную."+R);
  wr("\r\n"+HINT+"skip — пропустить шаг · quit — выйти."+R+"\r\n");
  showStep();
}
function showStep(){
  const s=tut.steps[tut.idx];
  if(s.note){ wr("\r\n"+DIM+"# "+s.note.replace(/\n/g,"\r\n# ")+R); }
  wr("\r\n\x1b[1mШаг "+(tut.idx+1)+"/"+tut.steps.length+"\x1b[0m — наберите (или Enter):\r\n");
  wr(CMDCOL+s.cmd.replace(/\n/g,"\r\n")+R);
  term.write("\r\n"+SH);
}
function runStep(input){
  const s=tut.steps[tut.idx];
  const inp=input.trim();
  if(inp==="quit"||inp==="exit"){ wr("\r\n\x1b[33mВыход из tutorial.\x1b[0m"); tut=null; term.write("\r\n"+PROMPT); return; }
  if(inp==="skip"){ wr("\r\n"+DIM+"(пропущено)"+R); return advance(); }
  const expectFirst=s.cmd.split("\n")[0].trim();
  if(inp && inp!==expectFirst && !s.cmd.trim().startsWith(inp)){
    wr("\r\n\x1b[33m≠ ожидалось:\x1b[0m "+expectFirst+"\r\n"+HINT+"(Enter — выполнить показанную, skip — дальше)"+R);
    term.write("\r\n"+SH); return;
  }
  if(s.out) wr("\r\n"+s.out);
  advance();
}
function advance(){
  tut.idx++;
  if(tut.idx>=tut.steps.length){
    wr("\r\n\r\n\x1b[1;32m✓ Готово! Стек "+tut.name+" развёрнут (симуляция).\x1b[0m");
    wr("\r\n"+DIM+"В реальности после этого данные текут source→sink. Проверьте target-БД."+R);
    tut=null; term.write("\r\n"+PROMPT); return;
  }
  showStep();
}

function run(input){
  const cmd=input.trim();
  if(tut){ runStep(input); line=""; return; }
  if(wiz){ wizAnswer(input); line=""; return; }
  if(cfg){ cfgAnswer(input); line=""; return; }
  if(!cmd){ prompt(); return; }
  hist.push(cmd); hi=hist.length;
  if(cmd==="clear"||cmd==="cls"){ term.clear(); prompt(); return; }
  if(cmd==="start"||cmd==="wizard"||cmd==="помощник"){ startWiz(); return; }
  if(cmd==="config"||cmd==="start-config"||cmd==="params"){ startCfg(); return; }
  if(cmd==="help"||cmd==="ls"){ wr("\r\n\x1b[1mС чего начать:\x1b[0m\r\n  "+CMDCOL+"start"+R+"        — помощник: подберёт настройку переливки по вашим ответам\r\n  "+CMDCOL+"config"+R+"       — как менять параметры (пресеты, профили, куда вписать)\r\n  "+CMDCOL+"tutorial"+R+"     — пошагово развернуть стенд\r\n\r\nСправка приложения ("+keys.length+" команд):\r\n  "+keys.join("\r\n  ")); prompt(); return; }
  if(cmd==="tutorial"||cmd==="tutorials"){ wr("\r\nВыберите: "+tutNames.map(n=>"tutorial "+n).join("\r\n")); prompt(); return; }
  if(cmd.startsWith("tutorial ")){ startTut(cmd.slice(9).trim()); return; }
  const out=CMDS[cmd];
  if(out!==undefined){ term.write("\r\n"+(MD_CMDS.has(cmd)?mdRender(out):out.replace(/\n/g,"\r\n"))); }
  else {
    const near=keys.filter(k=>k.startsWith(cmd.split(" ")[0])).slice(0,8);
    wr("\r\n\x1b[31mUnknown command:\x1b[0m "+cmd+(near.length?"\r\nПохожие: "+near.join("  "):"\r\nНаберите help")+"\r\n"+DIM+"(симуляция — доступны только вшитые команды)"+R);
  }
  prompt();
}

wr("\x1b[1mПесочница CDC Worker\x1b[0m — синхронизация данных между хранилищами (симуляция).\r\n\r\n"+
   "Не знаете продукт? Просто наберите "+CMDCOL+"start"+R+" — помощник задаст пару вопросов\r\n"+
   "(«откуда → куда переливаем?») и соберёт готовую команду.\r\n\r\n"+
   HINT+"Ещё: "+R+CMDCOL+"config"+R+HINT+" — как менять параметры · "+R+CMDCOL+"tutorial"+R+HINT+" — пошагово · "+R+CMDCOL+"help"+R+HINT+" — все команды · "+R+CMDCOL+"--help"+R+HINT+" — справка."+R);
term.write("\r\n"+PROMPT);

function complete(){
  const pool = (tut||wiz||cfg) ? [] : keys.concat(tutNames.map(n=>"tutorial "+n)).concat(["start","config","help","clear","tutorial"]);
  const m=pool.filter(k=>k.startsWith(line));
  if(m.length===1){ term.write(m[0].slice(line.length)); line=m[0]; }
  else if(m.length>1){
    let p=m[0]; for(const k of m){ while(!k.startsWith(p)) p=p.slice(0,-1); }
    if(p.length>line.length){ term.write(p.slice(line.length)); line=p; }
    else { wr("\r\n"+m.join("  ")); term.write("\r\n"+(tut?SH:PROMPT)+line); }
  }
}
// вставка: xterm.js отдаёт paste через onData; берём только первую строку в буфер ввода
term.onData(data=>{
  if(data.length<=1) return;              // одиночные символы идут через onKey
  const first=data.replace(/\r?\n.*$/s,"").replace(/[\x00-\x1f]/g,"");
  if(first){ line+=first; term.write(first); }
});

term.onKey(({key,domEvent:e})=>{
  if(e.key==="Enter"){ run(line); line=""; }
  else if(e.key==="Backspace"){ if(line.length){ line=line.slice(0,-1); term.write("\b \b"); } }
  else if(e.key==="Tab"){ e.preventDefault(); complete(); }
  else if(e.key==="ArrowUp"){ if(!tut&&!wiz&&!cfg&&hi>0){ hi--; term.write("\x1b[2K\r"+PROMPT+hist[hi]); line=hist[hi]; } }
  else if(e.key==="ArrowDown"){ if(!tut&&!wiz&&!cfg&&hi<hist.length-1){ hi++; term.write("\x1b[2K\r"+PROMPT+hist[hi]); line=hist[hi]; } else if(!tut&&!wiz&&!cfg){ hi=hist.length; term.write("\x1b[2K\r"+PROMPT); line=""; } }
  else if(key.length===1&&!e.ctrlKey&&!e.altKey&&!e.metaKey){ line+=key; term.write(key); }
});
</script></body></html>'''
html=html.replace("__CMDS__",CMDS).replace("__TUTS__",TUTS).replace("__SNIPS__",SNIPS)
open(sys.argv[3],"w",encoding="utf-8").write(html)
print("wrote",sys.argv[3],len(html),"bytes")
