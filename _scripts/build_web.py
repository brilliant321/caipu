# -*- coding: utf-8 -*-
"""
把「烹饪储备库」104 道菜打包成一个单文件手机网页（index.html）。
用法：python build_web.py
输出：烹饪储备库/index.html
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
                dishes.append({
                    "id": str(len(dishes)),
                    "name": fn[:-3],
                    "title": title,
                    "category": cat,
                    "ingredient": ing,
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
  --gold:#c8922f;
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
.search{margin-top:10px;position:relative}
.search input{width:100%;border:1px solid var(--line);background:var(--card);
  border-radius:12px;padding:11px 14px 11px 38px;font-size:15px;color:var(--ink);
  outline:none;box-shadow:0 1px 2px rgba(0,0,0,.04)}
.search input:focus{border-color:var(--accent)}
.search .ic{position:absolute;left:13px;top:50%;transform:translateY(-50%);
  color:var(--sub);font-size:15px}

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
  <div class="search">
    <span class="ic">🔍</span>
    <input id="q" type="search" placeholder="搜菜名 / 食材 / 分类，如「鱼香」「猪肉」" autocomplete="off">
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
</div>

<script>
const DATA = __DATA__;
const dishes = DATA.dishes;
const byId = {};
dishes.forEach(d => byId[d.id] = d);

const $ = id => document.getElementById(id);
function show(id){['view-home','view-cat','view-dish','view-guide'].forEach(v=>$(v).style.display='none');$(id).style.display='block';window.scrollTo(0,0);}

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
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}

/* ---- 导航 ---- */
function goHome(){location.hash='#/';}
function goCat(name){location.hash='#/c/'+encodeURIComponent(name);}
function goDish(id){location.hash='#/d/'+id;}
function goGuide(){location.hash='#/g';}
function goBack(){ const d=$('dishBody').dataset; if(d && d.cat) location.hash='#/c/'+encodeURIComponent(d.cat); else location.hash='#/'; }

function route(){
  const h=location.hash||'#/';
  if(h.startsWith('#/d/')){
    const id=h.slice(4); const d=byId[id];
    if(!d){goHome();return;}
    show('view-dish');
    $('dishBody').dataset.cat=d.category;
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
  $('q').value='';
}

/* ---- 搜索 ---- */
let timer=null;
$('q').addEventListener('input',()=>{
  clearTimeout(timer);
  timer=setTimeout(()=>{
    const kw=$('q').value.trim();
    if(!kw){ show('view-home'); renderHome(); return; }
    show('view-home');
    const k=kw.toLowerCase();
    const hit=dishes.filter(d=>
      d.name.toLowerCase().includes(k)||d.title.toLowerCase().includes(k)||
      d.ingredient.toLowerCase().includes(k)||d.category.toLowerCase().includes(k));
    $('catGrid').innerHTML='';
    $('totalCnt').textContent='';
    renderList(hit);
  },120);
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
