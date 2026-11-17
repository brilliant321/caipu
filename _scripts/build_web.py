# -*- coding: utf-8 -*-
"""
把「烹饪储备库」104 道菜打包成一个单文件手机网页（index.html）。
用法：python build_web.py
输出：烹饪储备库/index.html

支持两种检索模式：
1. 搜菜名 / 食材 / 分类（关键词）
2. 报原料 → 推荐菜（现有能做 / 需补购，含忌口·口味过滤）
"""
import os
import re
import json
import html as html_lib

from markdown import markdown as md_convert

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "index.html")

CAT_ICONS = {
    "蔬菜": "🥬",
    "水果": "🍎",
    "肉类": "🥩",
    "蛋类": "🥚",
    "奶制品": "🥛",
    "水产海鲜": "🦐",
    "豆制品": "🫘",
    "主食谷物": "🌾",
    "菌菇": "🍄",
    "调味香料": "🧂",
    "干货": "🥫",
    "坚果干果": "🥜",
}

CAT_ORDER = [
    "蔬菜", "水果", "肉类", "蛋类", "奶制品", "水产海鲜",
    "豆制品", "主食谷物", "菌菇", "调味香料", "干货", "坚果干果",
]

_wiki = re.compile(r"\[\[([^\]]+)\]\]")


def strip_wiki(text: str) -> str:
    return _wiki.sub(r"\1", text)


_list_item = re.compile(r"^\s*([-*+]|\d+[.)])\s+\S")


def normalize_lists(text: str) -> str:
    """列表项紧跟在段落/标题后面（无空行）时，Markdown 会把它当作文本。
    在「新起一个列表」的行前补空行，让编号步骤/要点正确渲染成 <ol>/<ul>。"""
    out = []
    for line in text.split("\n"):
        is_item = bool(_list_item.match(line))
        if is_item and out:
            prev = out[-1]
            prev_is_item = bool(_list_item.match(prev))
            if prev.strip() and not prev_is_item:
                out.append("")
        out.append(line)
    return "\n".join(out)


def cat_name_of(dirname: str) -> str:
    return dirname.split("_", 1)[1]


# ---------- 食材表解析（用于「报原料 → 推荐菜」） ----------

# 这些词本身不是食材（是备注/程度/处理方式），从食材名里剔除
NOISE_WORDS = {
    "去骨", "去皮", "去籽", "去壳", "去虾线", "去内脏",
    "切段", "切片", "切末", "切丝", "切丁", "剁碎", "剁末", "拍碎", "碾碎",
    "洗净", "泡软", "煮熟", "蒸熟", "焯水", "汆烫", "过油", "沥干",
    "适量", "少许", "各", "均可", "任选", "任选一种", "任选几种", "任选其一",
    "可选", "可加可不加", "备选", "装饰", "点缀", "约", "一些", "一点",
    "几个", "半个", "整", "大", "小", "等",
    "配菜", "配料", "主料", "辅料", "点缀料", "其他", "其它",
    "成品约", "分两次用", "分几次用",
}

_generic_num = re.compile(r"^[\d.~～\-–—]+$")


def _clean_token(t: str) -> str:
    t = strip_wiki(t).replace("**", "").strip()
    t = re.sub(r"[「」『』\"'`]", "", t)
    t = t.strip()
    if not t or _generic_num.match(t):
        return ""
    # 去掉尾部噪音词（如「豇豆均可」「小葱点缀」）
    for w in sorted(NOISE_WORDS, key=len, reverse=True):
        if t == w:
            return ""
        if t.endswith(w):
            t = t[: -len(w)].strip()
    if not t or _generic_num.match(t):
        return ""
    return t


def parse_cell(cell: str):
    """把食材表第一列的一格，解析成「组」的列表。
    一格 = 顿号/逗号分隔的多个「且」关系组；每组内 = 斜杠/「或」分隔的「或」关系别名。
    例：'葱、姜' -> [['葱'], ['姜']]
        '香醋（或白醋 / 苹果醋）' -> [['香醋', '白醋', '苹果醋']]
    返回：[[别名...], [别名...], ...]（外层是且，内层是或）"""
    groups = []
    for part in re.split(r"[、，,]", cell):
        part = part.strip()
        if not part:
            continue
        alts = []
        m = re.match(r"^(.*?)[（(]\s*(.*?)\s*[）)]$", part)
        if m and m.group(1).strip():
            main = _clean_token(m.group(1))
            if main:
                alts.append(main)
            inner = m.group(2)
            for sub in re.split(r"[/、，或]", inner):
                s = _clean_token(sub)
                if s:
                    alts.append(s)
        else:
            for sub in re.split(r"[/或]", part):
                s = _clean_token(sub)
                if s:
                    alts.append(s)
        # 去重、保序
        seen = []
        for a in alts:
            if a not in seen:
                seen.append(a)
        if seen:
            groups.append(seen)
    return groups


# 「可省略 / 可加可不加」的强标记：食材表里标了这些的料，不算「缺」、也可按忌口剔除
OPTIONAL_MARKERS = ("可选", "可不加", "可省略", "可以不加", "任选", "酌情", "随意")


def _row_optional(cells):
    """食材表一行（含用量/说明列）是否标了「可省略」。"""
    text = " ".join(cells[1:])
    return any(m in text for m in OPTIONAL_MARKERS)


def extract_first_ingredients(raw: str):
    """只取第一张食材表（初学版 / 唯一档）。
    返回 (groups, opt)：groups 每个是别名列表（外层且、内层或），opt 标记对应组是否可省略。"""
    out, opt = [], []
    in_t = False
    for line in raw.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            if in_t:
                break
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) >= 3 and cells[0] == "食材":
            in_t = True
            continue
        if not in_t:
            continue
        # 分隔行 |---|:---|---|
        if all(re.fullmatch(r"[-:]+", c) for c in cells):
            continue
        if cells[0]:
            is_opt = _row_optional(cells)
            for g in parse_cell(cells[0]):
                out.append(g)
                opt.append(is_opt)
    return out, opt


# ---------- 口味标签（用于忌口/口味匹配，如「不吃甜食」） ----------

# 甜味关键词（子串判断：糖/蜜/炼乳…）
SWEET_KEYS = ("糖", "蜜", "炼乳", "焦糖", "糖浆", "枫糖", "麦芽糖")
# 咸口关键词（子串判断，单向：关键词是食材名的子串）
SAVORY_KEYS = ("盐", "生抽", "老抽", "酱油", "蚝油", "醋", "料酒", "黄酒", "花雕酒",
               "辣椒", "豆瓣酱", "剁椒", "泡椒", "花椒", "胡椒", "味精", "鸡精", "咸")
# 明确甜点（含盐的点心也在此列出，兜底）
DESSERT_NAMES = {
    "冰糖雪梨", "香橙蒸蛋", "芒果西米露", "自制草莓酱", "自制葡萄汁",
    "脆皮炸香蕉", "双皮奶", "自制酸奶", "黄油曲奇", "肉桂卷",
    "葡萄干司康", "拔丝红薯", "拔丝苹果", "姜汁撞奶", "冰糖银耳羹",
    "杏仁豆腐", "琥珀核桃", "心太软", "黑芝麻糊",
}


def compute_tags(ings, name=""):
    """按用料判断口味标签。目前只算「甜」：明确甜点，或含甜味料且不含咸口料。"""
    flat = set()
    for g in ings:
        for a in g:
            flat.add(a)
    has_sweet = any(any(k in a for k in SWEET_KEYS) for a in flat)
    has_savory = any(any(k in a for k in SAVORY_KEYS) for a in flat)
    tags = []
    if name in DESSERT_NAMES or (has_sweet and not has_savory):
        tags.append("甜")
    return tags


def main():
    dishes = []
    for entry in sorted(os.listdir(ROOT)):
        if not os.path.isdir(os.path.join(ROOT, entry)):
            continue
        m = re.match(r"^(\d{2})_", entry)
        if not m:
            continue
        n = int(m.group(1))
        if not (1 <= n <= 12):
            continue
        cat = cat_name_of(entry)
        cat_path = os.path.join(ROOT, entry)
        for ing in sorted(os.listdir(cat_path)):
            cai_dir = os.path.join(cat_path, ing, "菜品")
            if not os.path.isdir(cai_dir):
                continue
            for fn in sorted(os.listdir(cai_dir)):
                if not fn.endswith(".md"):
                    continue
                fp = os.path.join(cai_dir, fn)
                raw = open(fp, encoding="utf-8").read()
                # 标题：取第一个 '# ' 行
                title = fn[:-3]
                for line in raw.splitlines():
                    if line.startswith("# "):
                        t = line[2:].strip()
                        if t:
                            title = t
                        break
                body = normalize_lists(strip_wiki(raw))
                body_html = md_convert(
                    body,
                    extensions=["tables", "sane_lists"],
                    output_format="html5",
                )
                ings, opt = extract_first_ingredients(raw)
                dishes.append({
                    "id": str(len(dishes)),
                    "name": fn[:-3],
                    "title": title,
                    "category": cat,
                    "ingredient": ing,
                    "ings": ings,
                    "opt": opt,
                    "tags": compute_tags(ings, fn[:-3]),
                    "html": body_html,
                })

    categories = [{"name": c, "icon": CAT_ICONS.get(c, "🍽")}
                  for c in CAT_ORDER if any(d["category"] == c for d in dishes)]

    # 入门总纲（新手必读）
    guide_html = ""
    guide_path = os.path.join(ROOT, "00_入门总纲", "入门总纲.md")
    if os.path.exists(guide_path):
        guide_html = md_convert(
            normalize_lists(strip_wiki(open(guide_path, encoding="utf-8").read())),
            extensions=["tables", "sane_lists"],
            output_format="html5",
        )

    data = {
        "total": len(dishes),
        "categories": categories,
        "dishes": dishes,
        "guide": guide_html,
    }
    payload = json.dumps(data, ensure_ascii=False)
    # 防止 </script> 提前闭合
    payload = payload.replace("</", "<\\/")

    out = TEMPLATE.replace("__DATA__", payload)
    open(OUT, "w", encoding="utf-8").write(out)
    print(f"OK 共 {len(dishes)} 道菜 -> {OUT}")
    print(f"文件大小 {os.path.getsize(OUT)/1024:.0f} KB")


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>烹饪储备库 · 菜谱手册</title>
<style>
:root{
  --bg:#faf6f0; --card:#ffffff; --ink:#2b2320; --sub:#8a7a6f;
  --line:#efe6db; --accent:#e05c2e; --accent-soft:#fbe7dd;
  --gold:#c8922f; --green:#3a7d44;
}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
  background:var(--bg);color:var(--ink);line-height:1.65;font-size:16px;
  -webkit-font-smoothing:antialiased;padding-bottom:env(safe-area-inset-bottom)}
a{color:var(--accent);text-decoration:none}

/* 顶栏 */
header{position:sticky;top:0;z-index:20;background:var(--bg);
  border-bottom:1px solid var(--line);padding:12px 16px 10px}
header .row{display:flex;align-items:center;gap:10px}
header .brand{font-weight:700;font-size:19px;white-space:nowrap}
header .brand small{display:block;font-weight:400;font-size:12px;color:var(--sub)}
.modes{display:flex;gap:8px;margin-top:10px}
.mode{flex:1;border:1px solid var(--line);background:var(--card);border-radius:10px;
  padding:8px 0;font-size:14px;color:var(--sub);cursor:pointer;text-align:center;transition:.12s}
.mode.on{background:var(--accent);color:#fff;border-color:var(--accent);font-weight:600}
.search{margin-top:10px;position:relative}
.search input{width:100%;border:1px solid var(--line);background:var(--card);
  border-radius:12px;padding:11px 14px 11px 38px;font-size:15px;color:var(--ink);
  outline:none;box-shadow:0 1px 2px rgba(0,0,0,.04)}
.search input:focus{border-color:var(--accent)}
.search .ic{position:absolute;left:13px;top:50%;transform:translateY(-50%);
  color:var(--sub);font-size:15px}
.ing-extra{margin-top:8px}
.ing-extra input{width:100%;border:1px solid var(--line);background:var(--card);
  border-radius:12px;padding:10px 14px;font-size:14px;color:var(--ink);outline:none}
.ing-extra input:focus{border-color:var(--accent)}
.hint{font-size:12px;color:var(--sub);margin-top:6px;padding:0 2px;line-height:1.5}

.wrap{max-width:720px;margin:0 auto;padding:14px 14px 40px}

/* 分类卡片 */
.sec-title{font-size:13px;color:var(--sub);margin:18px 2px 10px;font-weight:600;
  letter-spacing:.5px;display:flex;align-items:center;gap:8px}
.sec-title .cnt{margin-left:auto;font-weight:400}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
.cat{background:var(--card);border:1px solid var(--line);border-radius:14px;
  padding:13px 12px;cursor:pointer;transition:.12s;display:flex;align-items:center;gap:10px}
.cat:active{transform:scale(.97);background:var(--accent-soft)}
.cat .em{font-size:24px}
.cat .nm{font-weight:600;font-size:15px}
.cat .nm span{display:block;font-weight:400;font-size:12px;color:var(--sub)}

/* 菜品列表 */
.dish{background:var(--card);border:1px solid var(--line);border-radius:14px;
  padding:12px 14px;margin-bottom:10px;cursor:pointer;transition:.12s}
.dish:active{transform:scale(.98);background:var(--accent-soft)}
.dish .t{font-weight:600;font-size:16px}
.dish .m{font-size:12px;color:var(--sub);margin-top:2px}
.tag{display:inline-block;font-size:11px;color:var(--accent);background:var(--accent-soft);
  border-radius:6px;padding:1px 7px;margin-left:6px;vertical-align:1px}
.tag.ok{color:var(--green);background:#e7f2e8}
.dish .need{font-size:12px;color:var(--gold);margin-top:2px}
.dish .cut{font-size:12px;color:#1f8a70;margin-top:2px}
.dish .skip{font-size:12px;color:var(--sub);margin-top:1px}

/* 报原料结果 */
.sum{background:var(--accent-soft);border:1px solid var(--line);border-radius:12px;
  padding:10px 12px;font-size:13px;color:#7a4a30;margin-bottom:2px;line-height:1.6}

/* 详情页 */
.detail-head{background:var(--card);border:1px solid var(--line);border-radius:16px;
  padding:16px;margin-bottom:12px}
.detail-head h1{margin:0 0 6px;font-size:22px;line-height:1.3}
.detail-head .m{font-size:13px;color:var(--sub)}

/* 菜谱正文（markdown 渲染） */
.recipe{background:var(--card);border:1px solid var(--line);border-radius:16px;
  padding:16px 18px;overflow:hidden}
.recipe h1{font-size:20px;margin:.2em 0 .6em}
.recipe h2{font-size:17px;margin:1.4em 0 .6em;padding:8px 12px;
  background:var(--accent-soft);color:var(--accent);border-left:4px solid var(--accent);
  border-radius:0 8px 8px 0}
.recipe h2:first-of-type{margin-top:.3em}
.recipe h3{font-size:15px;margin:1.2em 0 .4em;color:#5a4638}
.recipe p{margin:.5em 0}
.recipe strong{color:#4a372a}
.recipe ul,.recipe ol{margin:.5em 0 .5em 0;padding-left:1.4em}
.recipe li{margin:.28em 0}
.recipe blockquote{margin:.7em 0;padding:8px 12px;background:#faf3ea;
  border-left:3px solid var(--gold);color:#6b5a4a;border-radius:0 8px 8px 0;font-size:14px}
.recipe table{border-collapse:collapse;width:100%;margin:.7em 0;font-size:14px;
  display:block;overflow-x:auto;-webkit-overflow-scrolling:touch}
.recipe table th,.recipe table td{border:1px solid var(--line);padding:7px 9px;
  text-align:left;vertical-align:top;white-space:normal}
.recipe table th{background:#f6efe6;font-weight:600}
.recipe hr{border:none;border-top:1px dashed var(--line);margin:1.2em 0}
.recipe a{word-break:break-all}

/* 空态 / 顶栏按钮 */
.empty{text-align:center;color:var(--sub);padding:40px 0;font-size:14px}
.back{background:var(--card);border:1px solid var(--line);border-radius:10px;
  padding:6px 12px;font-size:14px;color:var(--ink);cursor:pointer;white-space:nowrap}
.back:active{background:var(--accent-soft)}
.topbar{display:flex;align-items:center;gap:10px;margin-bottom:12px}
.topbar .crumb{font-weight:600;font-size:17px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
</style>
</head>
<body>
<header>
  <div class="row">
    <div class="brand">烹饪储备库<small id="subBrand">手机菜谱手册</small></div>
  </div>
  <div class="modes" id="modes">
    <button class="mode on" data-mode="search">🔍 搜菜名</button>
    <button class="mode" data-mode="ing">🧺 报原料</button>
  </div>
  <div class="search">
    <span class="ic" id="searchIc">🔍</span>
    <input id="q" type="search" placeholder="搜菜名 / 食材 / 分类，如「鱼香」「猪肉」" autocomplete="off">
  </div>
  <div class="ing-extra" id="ingExtra" style="display:none">
    <input id="taboo" type="text" placeholder="忌口 / 口味（可选）：不吃辣、不吃甜食、海鲜" autocomplete="off">
    <div class="hint" id="ingHint">输入现有原料（含调料），顿号/逗号/空格分隔。忌口「甜/糖/辣」会自动剔除可选料（如糖、辣椒），保住菜品主体；其它忌口命中即排除；偏好口味排前。</div>
  </div>
</header>

<div class="wrap">
  <!-- 首页 -->
  <div id="view-home">
    <div class="sec-title">📚 分类<span class="cnt" id="totalCnt"></span></div>
    <div class="grid" id="catGrid"></div>
    <div class="sec-title">🍳 全部菜品<span class="cnt" id="dishCnt"></span></div>
    <div id="dishList"></div>
    <div class="sec-title">🧭 新手必读</div>
    <div class="dish" id="openGuide">刀工 · 火候 · 调味三大基本功 + 术语说明（油温、断生、锅气…）</div>
    <div class="empty" id="noResult" style="display:none">没找到匹配的菜，换个词试试？</div>
  </div>

  <!-- 分类详情 -->
  <div id="view-cat" style="display:none">
    <div class="topbar"><button class="back" onclick="goHome()">‹ 返回</button>
      <span class="crumb" id="catCrumb"></span></div>
    <div id="catBody"></div>
  </div>

  <!-- 菜品详情 -->
  <div id="view-dish" style="display:none">
    <div class="topbar"><button class="back" onclick="goBack()">‹ 返回</button>
      <span class="crumb" id="dishCrumb"></span></div>
    <div id="dishBody"></div>
  </div>

  <!-- 入门总纲 -->
  <div id="view-guide" style="display:none">
    <div class="topbar"><button class="back" onclick="goHome()">‹ 返回</button>
      <span class="crumb">🧭 新手必读</span></div>
    <div class="recipe" id="guideBody"></div>
  </div>

  <!-- 报原料推荐 -->
  <div id="view-ing" style="display:none">
    <div class="topbar"><button class="back" onclick="goHome()">‹ 返回</button>
      <span class="crumb">🧺 报原料推荐</span></div>
    <div id="ingResult"></div>
  </div>
</div>

<script>
const DATA = __DATA__;
const dishes = DATA.dishes;
const byId = {};
dishes.forEach(d => byId[d.id] = d);

const $ = id => document.getElementById(id);
function show(id){['view-home','view-cat','view-dish','view-guide','view-ing'].forEach(v=>$(v).style.display='none');$(id).style.display='block';window.scrollTo(0,0);}
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}

/* ---- 首页 ---- */
function renderHome(){
  const cats = DATA.categories;
  $('totalCnt').textContent = DATA.total + ' 道菜';
  $('dishCnt').textContent = '';
  $('catGrid').innerHTML = cats.map(c=>{
    const n = dishes.filter(d=>d.category===c.name).length;
    return `<div class="cat" onclick="goCat('${esc(c.name)}')">
      <span class="em">${c.icon}</span><span class="nm">${esc(c.name)}<span>${n} 道菜</span></span></div>`;
  }).join('');
  renderList(dishes);
}
function renderList(list){
  $('dishCnt').textContent = list.length + ' 道';
  if(!list.length){ $('dishList').innerHTML=''; $('noResult').style.display='block'; return; }
  $('noResult').style.display='none';
  $('dishList').innerHTML = list.map(d=>
    `<div class="dish" onclick="goDish('${d.id}')">
      <div class="t">${esc(d.title)}<span class="tag">${esc(d.category)}</span></div>
      <div class="m">${esc(d.ingredient)} · 三档做法 · 点开看</div>
    </div>`).join('');
}

/* ---- 导航 ---- */
let mode = 'search';
let dishFromIng = false;
function goHome(){
  dishFromIng = false;
  $('q').value=''; $('taboo').value='';
  setMode('search');
  location.hash='#/';
}
function goCat(name){location.hash='#/c/'+encodeURIComponent(name);}
function goDish(id){
  dishFromIng = (mode==='ing' && $('q').value.trim()!=='');
  location.hash='#/d/'+id;
}
function goGuide(){location.hash='#/g';}
function goBack(){
  const d=$('dishBody').dataset;
  if(d && d.from==='ing'){ dishFromIng=false; show('view-ing'); renderIng(); window.scrollTo(0,0); return; }
  if(d && d.cat){ location.hash='#/c/'+encodeURIComponent(d.cat); }
  else location.hash='#/';
}

function route(){
  const h=location.hash||'#/';
  if(h.startsWith('#/d/')){
    const id=h.slice(4); const d=byId[id];
    if(!d){goHome();return;}
    show('view-dish');
    $('dishBody').dataset.cat=d.category;
    $('dishBody').dataset.from=(dishFromIng?'ing':'');
    $('dishCrumb').textContent=d.title;
    $('dishBody').innerHTML=
      `<div class="detail-head"><h1>${esc(d.title)}</h1>
       <div class="m">📂 ${esc(d.category)} · ${esc(d.ingredient)} · <span class="tag" onclick="goCat('${esc(d.category)}')">看同类</span></div></div>
       <div class="recipe">${d.html}</div>`;
  } else if(h.startsWith('#/c/')){
    const name=decodeURIComponent(h.slice(4));
    const list=dishes.filter(d=>d.category===name);
    if(!list.length){goHome();return;}
    show('view-cat');
    $('catCrumb').textContent=name;
    const byIng={};
    list.forEach(d=>{ (byIng[d.ingredient]=byIng[d.ingredient]||[]).push(d); });
    $('catBody').innerHTML=Object.keys(byIng).map(ing=>
      `<div class="sec-title">${ing}<span class="cnt">${byIng[ing].length} 道</span></div>`+
      byIng[ing].map(d=>
        `<div class="dish" onclick="goDish('${d.id}')">
           <div class="t">${esc(d.title)}</div>
           <div class="m">${esc(d.ingredient)} · 三档做法</div>
         </div>`).join('')).join('');
  } else if(h==='#/g'){
    show('view-guide');
    $('guideBody').innerHTML=DATA.guide||'<div class="empty">暂无内容</div>';
  } else {
    show('view-home'); renderHome();
  }
}

/* ---- 模式切换 ---- */
function setMode(m){
  mode = m;
  document.querySelectorAll('.mode').forEach(b=>b.classList.toggle('on', b.dataset.mode===m));
  $('ingExtra').style.display = (m==='ing') ? 'block' : 'none';
  $('searchIc').textContent = (m==='ing') ? '🧺' : '🔍';
  $('q').placeholder = (m==='ing') ? '输入现有原料：西红柿 鸡蛋 盐 油' : '搜菜名 / 食材 / 分类，如「鱼香」「猪肉」';
  onQuery();
}
$('modes').addEventListener('click', e=>{
  const b = e.target.closest('.mode'); if(!b) return;
  setMode(b.dataset.mode);
});

/* ---- 匹配工具 ---- */
function norm(s){return String(s).toLowerCase().replace(/[\s··：:；;、，,()（）\[\]{}<>.。／/]/g,'');}

// 同义/大类映射：key 为归一化后的词，value 为「类」；同类才算等价
const FAMILY = {
  // 猪
  '猪肉':'猪','五花肉':'猪','猪五花':'猪','猪肋排':'猪','猪排骨':'猪','排骨':'猪','肋排':'猪',
  '里脊':'猪','猪里脊':'猪','猪瘦肉':'猪','瘦肉':'猪','猪肉末':'猪','肉末':'猪','猪蹄':'猪',
  '后腿肉':'猪','前腿肉':'猪','梅花肉':'猪','猪颈肉':'猪','猪肚':'猪','猪肝':'猪',
  '腊肉':'猪','腊肠':'猪','香肠':'猪','火腿':'猪','火腿肠':'猪','培根':'猪','午餐肉':'猪','猪油':'猪油',
  // 牛
  '牛肉':'牛','牛里脊':'牛','牛柳':'牛','牛腩':'牛','牛腱':'牛','牛腱子':'牛','牛尾':'牛',
  '牛排':'牛','肥牛':'牛','牛肉末':'牛','牛肚':'牛',
  // 羊
  '羊肉':'羊','羊腿肉':'羊','羊肉卷':'羊','羊排':'羊','羊蝎子':'羊',
  // 禽
  '鸡肉':'鸡','鸡':'鸡','鸡腿':'鸡','鸡腿肉':'鸡','鸡胸':'鸡','鸡胸肉':'鸡','鸡翅':'鸡',
  '鸡翅中':'鸡','鸡翅根':'鸡','鸡爪':'鸡','鸡胗':'鸡','鸡心':'鸡','三黄鸡':'鸡','清远鸡':'鸡',
  '整鸡':'鸡','童子鸡':'鸡','鸡架':'鸡',
  '鸭肉':'鸭','鸭':'鸭','鸭腿':'鸭','半只鸭':'鸭','鸭翅':'鸭',
  // 蛋
  '鸡蛋':'蛋','蛋':'蛋','鸭蛋':'蛋','鹌鹑蛋':'蛋','皮蛋':'蛋','咸蛋':'蛋','蛋黄':'蛋','蛋白':'蛋',
  // 水产
  '虾':'虾','活虾':'虾','基围虾':'虾','明虾':'虾','虾仁':'虾','大虾':'虾','河虾':'虾','对虾':'虾','小龙虾':'虾','虾皮':'虾',
  '鱼':'鱼','鲈鱼':'鱼','草鱼':'鱼','鲤鱼':'鱼','鲫鱼':'鱼','带鱼':'鱼','黄花鱼':'鱼','黄鱼':'鱼',
  '三文鱼':'鱼','巴沙鱼':'鱼','龙利鱼':'鱼','黑鱼':'鱼','鲢鱼':'鱼','胖头鱼':'鱼','鱼片':'鱼','鱼头':'鱼',
  '鱿鱼':'海鲜','章鱼':'海鲜','墨鱼':'海鲜','螃蟹':'海鲜','蟹':'海鲜','蛤蜊':'海鲜','花甲':'海鲜',
  '扇贝':'海鲜','生蚝':'海鲜','海带':'海鲜','紫菜':'海鲜',
  // 蔬菜
  '西红柿':'番茄','番茄':'番茄',
  '土豆':'土豆','马铃薯':'土豆','洋芋':'土豆',
  '青椒':'青椒','尖椒':'青椒','螺丝椒':'青椒','薄皮青椒':'青椒','柿子椒':'青椒','线椒':'青椒','杭椒':'青椒',
  '彩椒':'彩椒','甜椒':'彩椒','红椒':'彩椒',
  '蒜':'蒜','大蒜':'蒜','蒜头':'蒜','蒜瓣':'蒜','独头蒜':'蒜','蒜末':'蒜','蒜片':'蒜',
  '蒜苗':'蒜苗','青蒜':'蒜苗',
  '姜':'姜','生姜':'姜','老姜':'姜','嫩姜':'姜','姜片':'姜','姜末':'姜','姜丝':'姜',
  '葱':'葱','小葱':'葱','大葱':'葱','香葱':'葱','青葱':'葱','葱白':'葱','葱花':'葱','葱段':'葱','洋葱':'洋葱',
  '香菜':'香菜','黄瓜':'黄瓜',
  '茄子':'茄子','长茄子':'茄子','圆茄子':'茄子','紫长茄':'茄子',
  '豆角':'豆角','四季豆':'豆角','豇豆':'豆角','长豆角':'豆角',
  '豆腐':'豆腐','嫩豆腐':'豆腐','内酯豆腐':'豆腐','老豆腐':'豆腐','北豆腐':'豆腐','南豆腐':'豆腐',
  '豆腐皮':'豆皮','豆皮':'豆皮','千张':'豆皮','豆腐干':'豆干','豆干':'豆干','香干':'豆干',
  '白菜':'白菜','大白菜':'白菜','娃娃菜':'白菜','圆白菜':'包菜','包菜':'包菜','卷心菜':'包菜','甘蓝':'包菜',
  '青菜':'青菜','小青菜':'青菜','上海青':'青菜','油菜':'青菜','小白菜':'青菜',
  '口蘑':'菌菇','香菇':'菌菇','金针菇':'菌菇','杏鲍菇':'菌菇','平菇':'菌菇','白玉菇':'菌菇','蟹味菇':'菌菇','蘑菇':'菌菇','木耳':'菌菇','银耳':'菌菇',
  '胡萝卜':'胡萝卜','白萝卜':'白萝卜','萝卜':'萝卜','青萝卜':'萝卜',
  '玉米':'玉米','玉米粒':'玉米','青豆':'青豆','豌豆':'豌豆','毛豆':'毛豆',
  '山药':'山药','莲藕':'莲藕','藕':'莲藕','竹笋':'笋','笋':'笋','冬笋':'笋','春笋':'笋',
  '西葫芦':'西葫芦','苦瓜':'苦瓜','丝瓜':'丝瓜','冬瓜':'冬瓜','南瓜':'南瓜','红薯':'红薯','地瓜':'红薯','芋头':'芋头',
  '芹菜':'芹菜','西芹':'芹菜','韭菜':'韭菜','菠菜':'菠菜','生菜':'生菜','空心菜':'空心菜','茼蒿':'茼蒿','莴笋':'莴笋',
  '西兰花':'西兰花','花菜':'花菜','菜花':'花菜',
  // 调味料
  '油':'油','食用油':'油','植物油':'油','花生油':'油','菜籽油':'油','玉米油':'油','色拉油':'油','调和油':'油','大豆油':'油','葵花籽油':'油',
  '香油':'香油','芝麻油':'香油','麻油':'香油','黄油':'黄油',
  '盐':'盐','食盐':'盐','海盐':'盐',
  '糖':'糖','白糖':'糖','白砂糖':'糖','砂糖':'糖','冰糖':'糖','红糖':'糖','绵白糖':'糖',
  '蜂蜜':'糖','炼乳':'糖','焦糖':'糖','糖浆':'糖','枫糖':'糖','麦芽糖':'糖',
  '酱油':'酱油','生抽':'酱油','老抽':'酱油','蒸鱼豉油':'酱油','味极鲜':'酱油','鲜味汁':'酱油',
  '醋':'醋','香醋':'醋','陈醋':'醋','米醋':'醋','白醋':'醋','苹果醋':'醋','9度米醋':'醋',
  '料酒':'料酒','黄酒':'料酒','花雕酒':'料酒',
  '淀粉':'淀粉','生粉':'淀粉','玉米淀粉':'淀粉','土豆淀粉':'淀粉','红薯淀粉':'淀粉','木薯淀粉':'淀粉','澄粉':'淀粉',
  '蚝油':'蚝油','黑胡椒':'胡椒','白胡椒':'胡椒','黑胡椒粉':'胡椒','白胡椒粉':'胡椒','胡椒':'胡椒',
  '花椒':'花椒','藤椒':'花椒','麻椒':'花椒',
  '辣椒':'辣','干辣椒':'辣','小米辣':'辣','小米椒':'辣','辣椒油':'辣','辣椒粉':'辣','辣椒面':'辣',
  '豆瓣酱':'辣','红油豆瓣':'辣','剁椒':'辣','泡椒':'辣','油泼辣子':'辣','红油':'辣',
  '味精':'味精','鸡精':'味精','五香粉':'五香粉','孜然':'孜然','孜然粉':'孜然',
  '甜':'甜','甜食':'甜','甜品':'甜','甜点':'甜','糖水':'甜',
  '八角':'香料','桂皮':'香料','香叶':'香料','丁香':'香料','草果':'香料','小茴香':'香料',
  '白芷':'香料','陈皮':'香料','豆蔻':'香料','砂仁':'香料','甘草':'香料','山奈':'香料','花椒粉':'花椒'
};
// 反向索引：类名 -> 该类的所有成员词
const MEMBERS = {};
Object.keys(FAMILY).forEach(k => { (MEMBERS[FAMILY[k]] = MEMBERS[FAMILY[k]] || []).push(k); });
const FAMILY_IDS = new Set(Object.values(FAMILY));
function hasFam(s){ const n=norm(s); return Object.prototype.hasOwnProperty.call(FAMILY,n) || FAMILY_IDS.has(n); }
function familyOf(s){
  const n = norm(s);
  return Object.prototype.hasOwnProperty.call(FAMILY, n) ? FAMILY[n] : n;
}
function matchIng(alt, tok){
  const a=norm(alt), t=norm(tok);
  if(!a||!t) return false;
  const fa=familyOf(alt), ft=familyOf(tok);
  const aKnown=hasFam(alt), tKnown=hasFam(tok);
  if(aKnown && tKnown) return fa===ft;
  if(a===t || a.includes(t) || t.includes(a)) return true;
  // 一侧已知、一侧未知：未知侧只要「包含」已知侧某个同类成员，即算等价
  if(aKnown){ const mem=MEMBERS[fa]||[a]; if(mem.some(m=>t.includes(m)||m.includes(t))) return true; }
  if(tKnown){ const mem=MEMBERS[ft]||[t]; if(mem.some(m=>a.includes(m)||m.includes(a))) return true; }
  return false;
}
function parseTokens(s){return String(s).split(/[、，,;；\s]+/).map(x=>x.trim()).filter(Boolean);}

function dishMatchWord(d, w){
  const cands = [d.title, d.name, d.category, d.ingredient].concat((d.ings||[]).flat(), (d.tags||[]));
  return cands.some(c=>matchIng(c, w));
}
function parseTaboo(s){
  const excl=[], incl=[];
  const NEG=/^(不吃|不要吃|不想要|不要|忌口|忌|讨厌|别|免|无|不喜|怕|不)/;
  parseTokens(s).forEach(raw=>{
    const neg = NEG.test(raw);
    const word = raw.replace(NEG,'').trim();
    if(word){ (neg?excl:incl).push(word); }
  });
  return {excl, incl};
}

/* ---- 软忌口（甜 / 糖 / 辣）：可剔除「可选料」、只对「必需料/菜名/标签」整体排除 ---- */
const SOFT_TABOOS = new Set(['甜','甜食','甜品','甜点','糖水','糖','白糖','白砂糖','砂糖','冰糖','红糖','绵白糖','蜂蜜','炼乳','焦糖','糖浆','枫糖','麦芽糖','辣','辣椒','香辣','麻辣']);
// 甜类忌口：只排除「甜点/甜口菜」，并剔除「可选糖」；不因「必需糖」排除咸口菜（糖醋排骨/红烧肉/西红柿炒蛋不算「甜食」）
const SWEET_TABOOS = new Set(['甜','甜食','甜品','甜点','糖水']);
// 甜类忌口要能关联到「糖」类原料（FAMILY 里甜/糖是两族，这里补一条桥；辣类已由 FAMILY 覆盖）
const SOFT_TABOO_FAMS = {'甜':['糖'],'甜食':['糖'],'甜品':['糖'],'甜点':['糖'],'糖水':['糖']};
function tabooConflictFams(w){
  const n = norm(w);
  if(Object.prototype.hasOwnProperty.call(SOFT_TABOO_FAMS, n)) return SOFT_TABOO_FAMS[n];
  if(FAMILY_IDS.has(n)) return [familyOf(w)];
  return [];
}
// 返回 { action: 'keep' | 'exclude' | 'adapt', removedIdx: [可选料所在组下标] }
function tabooVerdict(d, w){
  const n = norm(w);
  // 硬忌口（海鲜/牛/羊/花生…）：命中即排除（沿用旧逻辑）
  if(!SOFT_TABOOS.has(n)){
    return dishMatchWord(d, w) ? {action:'exclude'} : {action:'keep'};
  }
  // 软忌口
  const idCands = [d.title, d.name, d.ingredient, d.category].concat(d.tags||[]);
  if(idCands.some(c=>matchIng(c, w))) return {action:'exclude'};
  const fams = tabooConflictFams(w);
  const groups = (d.ings && d.ings.length) ? d.ings : [[d.ingredient]];
  const removedIdx = [];
  let hitCore = false;
  groups.forEach((g,i)=>{
    const hit = g.find(a => matchIng(a, w) || fams.some(f => matchIng(a, f)));
    if(!hit) return;
    const opt = d.opt && d.opt[i];
    if(opt) removedIdx.push(i);
    else if(!SWEET_TABOOS.has(n)) hitCore = true; // 甜类忌口：必需糖不算命中（提鲜/糖醋不算「甜食」）
  });
  if(hitCore) return {action:'exclude'};
  if(removedIdx.length) return {action:'adapt', removedIdx};
  return {action:'keep'};
}

/* ---- 报原料 → 推荐菜 ---- */
// 水默认随时有，不算「需补购」（其余调料按用户要求：全都要报）
const ALWAYS = new Set(['水','开水','清水','凉开水','温水','热水','冷水','纯净水','凉白开']);
function dishCard(d){
  const ok = d._can ? '<span class="tag ok">✅ 能做</span>' : '';
  const miss = d._can ? '' : `<div class="need">🛒 缺：${d._missingNames.join('、')}</div>`;
  const cut = (d._cutNames && d._cutNames.length) ? `<div class="cut">✂️ 已按忌口去掉：${d._cutNames.join('、')}</div>` : '';
  const skip = (d._skipNames && d._skipNames.length) ? `<div class="skip">◽ 可不加：${d._skipNames.join('、')}</div>` : '';
  return `<div class="dish" onclick="goDish('${d.id}')">
    <div class="t">${esc(d.title)}<span class="tag">${esc(d.category)}</span>${ok}</div>
    <div class="m">${esc(d.ingredient)} · 匹配 ${d._matched}/${d._total} 样（必需料）</div>${miss}${cut}${skip}
  </div>`;
}
function renderIng(){
  const toks = parseTokens($('q').value);
  if(!toks.length){ show('view-home'); renderHome(); return; }
  show('view-ing');
  const {excl, incl} = parseTaboo($('taboo').value);

  // 1) 忌口：硬忌口命中即排除；软忌口（甜/糖/辣）命中「可选料」→ 剔除、命中「必需料/菜名/标签」→ 排除
  const pool = [];
  dishes.forEach(d=>{
    const removedIdx = new Set();
    let drop = false;
    for(const w of excl){
      const v = tabooVerdict(d, w);
      if(v.action==='exclude'){ drop = true; break; }
      if(v.action==='adapt'){ v.removedIdx.forEach(i=>removedIdx.add(i)); }
    }
    if(drop) return;
    d._removedIdx = removedIdx;
    pool.push(d);
  });

  // 2) 算匹配度 + 口味偏好命中数（可选料不算缺、不计入「匹配分母」）
  pool.forEach(d=>{
    const groups = (d.ings && d.ings.length) ? d.ings : [[d.ingredient]];
    const opt = d.opt || [];
    let matched=0, total=0; const missNames=[], cutNames=[], skipNames=[];
    groups.forEach((g,i)=>{
      if(g.some(a=>ALWAYS.has(norm(a)))){ total++; matched++; return; } // 水默认有
      if(opt[i]){ // 可选料：不做「缺」，按是否被忌口命中分「去掉/可不加」
        if(d._removedIdx && d._removedIdx.has(i)) cutNames.push(g[0]);
        else skipNames.push(g[0]);
        return;
      }
      total++;
      if(g.some(a=>toks.some(t=>matchIng(a,t)))){ matched++; }
      else missNames.push(g[0]);
    });
    d._matched=matched; d._total=total;
    d._can = (missNames.length===0);
    d._missingNames = missNames;
    d._cutNames = cutNames;
    d._skipNames = skipNames;
    d._taste = incl.filter(w=>dishMatchWord(d,w)).length;
  });

  // 3) 排序：口味偏好命中数 ↓ → 原料匹配度 ↓ → 缺的少 ↓
  pool.sort((a,b)=>
    (b._taste - a._taste) ||
    ((b._total ? b._matched/b._total : 1) - (a._total ? a._matched/a._total : 1)) ||
    (a._missingNames.length - b._missingNames.length) ||
    (a.title<b.title?-1:1)
  );

  const canCount = pool.filter(d=>d._can).length;
  const cutCount = pool.filter(d=>d._cutNames && d._cutNames.length).length;
  const tag=[];
  if(excl.length) tag.push('忌口：'+excl.join('、'));
  if(incl.length) tag.push('偏好：'+incl.join('、'));
  let html = `<div class="sum">你报了 <b>${toks.length}</b> 样原料${tag.length?'，'+tag.join(' · '):''}。<br>命中 <b>${pool.length}</b> 道，按「口味偏好 → 原料匹配度」排序：✅能做 <b>${canCount}</b> 道 · 🛒需补购 <b>${pool.length-canCount}</b> 道${cutCount?' · ✂️已按忌口自动去料 <b>'+cutCount+'</b> 道':''}。</div>`;

  html += pool.length ? pool.map(dishCard).join('')
    : `<div class="empty">没找到符合的菜（可能忌口把菜都排掉了），换个原料或忌口试试。</div>`;
  $('ingResult').innerHTML = html;
}

/* ---- 搜索（搜菜名模式） ---- */
let timer=null;
function onQuery(){
  const kw=$('q').value.trim();
  if(mode==='ing'){ renderIng(); return; }
  if(!kw){ show('view-home'); renderHome(); return; }
  show('view-home');
  const k=kw.toLowerCase();
  const hit=dishes.filter(d=>
    d.name.toLowerCase().includes(k)||d.title.toLowerCase().includes(k)||
    d.ingredient.toLowerCase().includes(k)||d.category.toLowerCase().includes(k));
  $('catGrid').innerHTML='';
  $('totalCnt').textContent='';
  renderList(hit);
}
$('q').addEventListener('input',()=>{
  clearTimeout(timer);
  timer=setTimeout(onQuery,120);
});
$('taboo').addEventListener('input',()=>{
  clearTimeout(timer);
  timer=setTimeout(onQuery,120);
});

$('openGuide').onclick=goGuide;
window.addEventListener('hashchange',route);
route();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
