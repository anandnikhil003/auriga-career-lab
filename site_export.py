"""Static website generator for Auriga Career Lab (additive — extends the old
--export-site). Produces a modern, responsive, GitHub-Pages-ready site that ALSO
hosts the Instagram card images.

Only this module changes. The pipeline (QR encoder, publishers, analytics, db,
scheduler, dedup, verification) is untouched — we merely READ from it.

  python main.py --export-site

Outputs (all regenerated every run):
  site/index.html  about.html  opportunities.html  categories.html  contact.html
  site/assets/css/style.css   site/assets/js/main.js
  site/assets/images/cards/<category>/*.png      (copied slides)
  site/assets/images/qr/<id>.png                 (one QR per opportunity)
  site/opportunities.json    site/stats.json
  site/README_DEPLOY.md
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import date, datetime

import cards
import config
import scrapers


# ───────────────────────────── data layer ──────────────────────────────────
def _country_main(country: str) -> str:
    return (country or "Global").split(" / ")[0].split(",")[0].strip() or "Global"


def build_data():
    """Returns (items, stats). items = list of plain dicts the site reads."""
    first_seen, posted = {}, set()
    scheduled_today, remaining, total_db, db_kb = 0, None, None, 0.0
    try:
        import db
        conn = db.connect()
        for r in conn.execute("SELECT fingerprint, first_seen, posted_date "
                              "FROM opportunities"):
            first_seen[r["fingerprint"]] = r["first_seen"]
            if r["posted_date"]:
                posted.add(r["fingerprint"])
        st = db.stats(conn)
        total_db, remaining = st["total"], st["remaining"]
        scheduled_today = len({x["category"] for x in db.todays_facebook_posts(conn)})
        db_kb = (os.path.getsize(config.DB_PATH) / 1024) if os.path.exists(config.DB_PATH) else 0.0
        conn.close()
    except Exception:
        pass

    import scoring
    items = []
    for o in scrapers.collect():
        o.first_seen = first_seen.get(o.fingerprint)
        scoring.score(o)
        items.append({
            "id": o.fingerprint,
            "program": o.program,
            "organization": o.organization,
            "country": o.country or "Global",
            "country_main": _country_main(o.country),
            "funding": o.funding or "Fully funded — see official page",
            "is_funded": bool(o.is_funded),
            "deadline": o.deadline.isoformat() if o.deadline else "Rolling",
            "deadline_iso": o.deadline.isoformat() if o.deadline else None,
            "category": o.category,
            "category_label": config.CATEGORIES.get(o.category, o.category),
            "description": o.description or o.eligibility or "",
            "url": o.official_url,
            "tier": o.tier,
            "score": o.score,
            "added": o.first_seen or date.today().isoformat(),
            "qr": f"assets/images/qr/{o.fingerprint}.png",
        })

    items.sort(key=lambda i: (i["added"], i["score"]), reverse=True)
    stats = {
        "total": total_db if total_db is not None else len(items),
        "catalog_size": len(items),
        "remaining": remaining if remaining is not None else len(items),
        "scheduled_today": scheduled_today,
        "db_size_kb": round(db_kb, 1),
        "countries": len({i["country_main"] for i in items}),
        "organizations": len({i["organization"] for i in items if i["organization"]}),
        "funded": sum(1 for i in items if i["is_funded"]),
        "by_category": {c: sum(1 for i in items if i["category"] == c) for c in config.CATEGORIES},
        "category_labels": dict(config.CATEGORIES),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "sample_card": None,
    }
    return items, stats


def _qr_for(items, qr_dir):
    qr_dir.mkdir(parents=True, exist_ok=True)
    for it in items:
        out = qr_dir / f"{it['id']}.png"
        try:
            cards.qr_image(it["url"], scale=4, border=2).save(out, "PNG")
        except Exception:
            pass


def _copy_cards(img_dir):
    """Copy generated slide images into the site and return a sample card path."""
    dest = img_dir / "cards"
    sample = None
    for cat in config.CATEGORIES:
        src = config.CARDS_DIR / cat
        if not src.exists():
            continue
        (dest / cat).mkdir(parents=True, exist_ok=True)
        for png in sorted(src.glob("*.png"), key=lambda x: x.name):
            shutil.copy2(png, dest / cat / png.name)
            rel = f"assets/images/cards/{cat}/{png.name}"
            if sample is None and png.name != "0_cover.png":
                sample = rel
            if sample is None:
                sample = rel
    return sample


# ──────────────────────────────── CSS ──────────────────────────────────────
_CSS = r""":root{
  --navy:#0b1b34; --navy2:#11254a; --blue:#2f6fed; --blue-l:#5e8bf7;
  --bg:#0e1726; --panel:#15233c; --panel2:#1b2c49; --ink:#e8eef7; --mut:#9fb3c8;
  --accent:#5ec8f5; --green:#86dc96; --radius:16px; --shadow:0 8px 30px rgba(0,0,0,.25);
}
*{box-sizing:border-box} html{scroll-behavior:smooth}
body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;
  background:linear-gradient(180deg,#0c1626,#0e1726);color:var(--ink);line-height:1.55}
a{color:var(--blue-l);text-decoration:none} img{max-width:100%;display:block}
.container{max-width:1180px;margin:0 auto;padding:0 20px}
/* nav */
.nav{position:sticky;top:0;z-index:50;background:rgba(11,27,52,.92);
  backdrop-filter:blur(8px);border-bottom:1px solid #1d2c44}
.nav .container{display:flex;align-items:center;justify-content:space-between;height:64px}
.brand{display:flex;align-items:center;gap:10px;font-weight:800;color:#fff;font-size:18px}
.brand .logo{width:34px;height:34px;border-radius:9px;background:linear-gradient(135deg,var(--blue),var(--accent));
  display:grid;place-items:center;color:#06122a;font-weight:900}
.nav ul{display:flex;gap:22px;list-style:none;margin:0;padding:0}
.nav a{color:var(--mut);font-weight:600} .nav a.active,.nav a:hover{color:#fff}
.burger{display:none;background:none;border:0;color:#fff;font-size:24px;cursor:pointer}
/* hero */
.hero{padding:70px 0 50px;display:grid;grid-template-columns:1.1fr .9fr;gap:40px;align-items:center}
.hero h1{font-size:46px;line-height:1.1;margin:0 0 14px;color:#fff;letter-spacing:-.5px}
.hero p.sub{font-size:19px;color:var(--mut);margin:0 0 26px;max-width:540px}
.cta{display:flex;gap:14px;flex-wrap:wrap}
.btn{display:inline-block;padding:12px 22px;border-radius:30px;font-weight:700;border:1px solid transparent;cursor:pointer}
.btn.primary{background:linear-gradient(135deg,var(--blue),var(--accent));color:#06122a}
.btn.ghost{border-color:#33486e;color:#cfe0f5;background:transparent}
.hero-card{background:var(--panel);border-radius:var(--radius);box-shadow:var(--shadow);
  border:1px solid #20304f;overflow:hidden;transform:rotate(-1.5deg)}
.hero-card img{width:100%}
.eyebrow{color:var(--accent);font-weight:800;letter-spacing:2px;text-transform:uppercase;font-size:13px}
/* sections */
section.block{padding:46px 0}
h2.title{font-size:30px;color:#fff;margin:0 0 6px} .lead{color:var(--mut);margin:0 0 26px}
/* stats */
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}
.stat{background:var(--panel);border:1px solid #20304f;border-radius:var(--radius);padding:20px;text-align:center}
.stat .n{font-size:30px;font-weight:800;color:#fff}.stat .l{color:var(--mut);font-size:13px;margin-top:4px}
/* category cards */
.cats{display:grid;grid-template-columns:repeat(5,1fr);gap:14px}
.cat-card{background:var(--panel);border:1px solid #20304f;border-radius:var(--radius);padding:22px 16px;text-align:center;transition:.15s}
.cat-card:hover{transform:translateY(-4px);border-color:var(--blue)}
.cat-card .ic{font-size:30px}.cat-card .nm{font-weight:800;color:#fff;margin:8px 0 2px}.cat-card .ct{color:var(--mut);font-size:13px}
/* opportunity grid */
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:18px}
.opp{background:var(--panel);border:1px solid #20304f;border-radius:var(--radius);padding:18px;display:flex;flex-direction:column;gap:10px;box-shadow:var(--shadow)}
.opp .top{display:flex;justify-content:space-between;gap:10px}
.opp h3{margin:0;font-size:18px;color:#fff;line-height:1.25}
.opp .org{color:var(--mut);font-size:14px}
.tag{display:inline-block;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:700}
.tag.cat{background:#1d3a63;color:#9cc8ff}.tag.fund{background:#193a23;color:var(--green)}
.tag.cty{background:#26344f;color:#cfe0f5}.tag.dl{background:#3a2a17;color:#f5c46a}
.opp .desc{color:#cdd9ea;font-size:14px;flex:1}
.opp .row{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:6px}
.opp .qr{width:84px;height:84px;border-radius:10px;background:#fff;padding:5px}
.opp .apply{background:linear-gradient(135deg,var(--blue),var(--accent));color:#06122a;padding:10px 18px;border-radius:24px;font-weight:800}
.badges{display:flex;gap:6px;flex-wrap:wrap}
/* toolbar */
.toolbar{display:grid;grid-template-columns:1.4fr repeat(4,1fr);gap:10px;margin-bottom:22px}
.toolbar input,.toolbar select{background:var(--panel2);border:1px solid #2a3c5e;color:var(--ink);
  padding:11px 12px;border-radius:12px;font-size:14px;width:100%}
.count{color:var(--mut);margin:0 0 14px}
/* about/contact */
.prose{max-width:820px}.prose h2{color:#fff;margin-top:30px}.prose p,.prose li{color:#cdd9ea}
.card-panel{background:var(--panel);border:1px solid #20304f;border-radius:var(--radius);padding:24px}
.form label{display:block;margin:14px 0 6px;color:var(--mut);font-weight:600}
.form input,.form textarea{width:100%;background:var(--panel2);border:1px solid #2a3c5e;color:var(--ink);padding:12px;border-radius:12px}
.socials{display:flex;gap:12px;flex-wrap:wrap;margin-top:16px}
.socials a{background:var(--panel2);border:1px solid #2a3c5e;padding:10px 16px;border-radius:24px;color:#cfe0f5;font-weight:700}
/* footer */
footer{border-top:1px solid #1d2c44;margin-top:40px;padding:34px 0;color:var(--mut)}
footer .container{display:flex;justify-content:space-between;flex-wrap:wrap;gap:16px}
.empty{color:var(--mut);padding:40px;text-align:center;grid-column:1/-1}
/* responsive */
@media(max-width:980px){.hero{grid-template-columns:1fr}.stats{grid-template-columns:repeat(2,1fr)}
  .cats{grid-template-columns:repeat(2,1fr)}.toolbar{grid-template-columns:1fr 1fr}}
@media(max-width:640px){.nav ul{display:none;position:absolute;top:64px;left:0;right:0;flex-direction:column;
  background:var(--navy);padding:14px 20px;border-bottom:1px solid #1d2c44}.nav ul.open{display:flex}
  .burger{display:block}.hero h1{font-size:34px}.stats{grid-template-columns:1fr 1fr}
  .cats{grid-template-columns:1fr}.toolbar{grid-template-columns:1fr}}
"""


# ──────────────────────────────── JS ───────────────────────────────────────
_JS = r"""const $=(s,r=document)=>r.querySelector(s);
const $$=(s,r=document)=>[...r.querySelectorAll(s)];
let OPPS=[],STATS={};
const ICONS={stem:'🔬',ug_research:'📚',ai_cs:'🤖',scholarships:'🎓',conferences:'🎤'};
const esc=s=>(s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

async function boot(){
  try{
    OPPS=await fetch('opportunities.json').then(r=>r.json());
    STATS=await fetch('stats.json').then(r=>r.json());
  }catch(e){console.error('Could not load data',e);}
  // mobile nav
  const b=$('.burger'); if(b)b.onclick=()=>$('.nav ul').classList.toggle('open');
  widgets();
  const page=document.body.dataset.page;
  if(page==='home'){latest();featured();hero();catCounts();}
  if(page==='opportunities')oppsPage();
  if(page==='categories')catCounts();
}

function fundedText(o){return o.is_funded?'Fully Funded':'Funding varies';}
function card(o){
  return `<article class="opp">
    <div class="top"><h3>${esc(o.program)}</h3></div>
    <div class="org">${esc(o.organization)}</div>
    <div class="badges">
      <span class="tag cat">${esc(o.category_label)}</span>
      <span class="tag cty">${esc(o.country_main)}</span>
      ${o.is_funded?'<span class="tag fund">Fully Funded</span>':''}
      <span class="tag dl">${esc(o.deadline)}</span>
    </div>
    <p class="desc">${esc(o.description)}</p>
    <div class="row">
      <a class="apply" href="${esc(o.url)}" target="_blank" rel="noopener">Apply →</a>
      <img class="qr" src="${esc(o.qr)}" alt="QR to ${esc(o.program)}" loading="lazy"
        onerror="this.style.display='none'">
    </div></article>`;
}
function render(list,el){
  el.innerHTML = list.length?list.map(card).join(''):'<div class="empty">No opportunities match your filters.</div>';
}

function widgets(){
  const set=(id,v)=>{const e=document.getElementById(id);if(e)e.textContent=v;};
  set('stat-total',STATS.catalog_size??OPPS.length);
  set('stat-remaining',STATS.remaining??'—');
  set('stat-scheduled',(STATS.scheduled_today??0)+' / 5');
  set('stat-dbsize',(STATS.db_size_kb??0)+' KB');
  set('stat-countries',STATS.countries??new Set(OPPS.map(o=>o.country_main)).size);
  set('stat-orgs',STATS.organizations??new Set(OPPS.map(o=>o.organization)).size);
  set('stat-funded',STATS.funded??OPPS.filter(o=>o.is_funded).length);
  set('stat-updated',STATS.generated_at||'');
}
function latest(){const el=$('#latest');if(el)render(OPPS.slice(0,6),el);}
function featured(){const el=$('#featured');if(!el)return;
  render([...OPPS].sort((a,b)=>(a.tier-b.tier)||(b.score-a.score)).slice(0,6),el);}
function hero(){const i=$('#hero-img');if(i&&STATS.sample_card)i.src=STATS.sample_card;}
function catCounts(){
  $$('[data-catcount]').forEach(e=>{const k=e.dataset.catcount;
    e.textContent=(STATS.by_category&&STATS.by_category[k]!=null)?STATS.by_category[k]:
      OPPS.filter(o=>o.category===k).length;});
}

function oppsPage(){
  const grid=$('#opps'),q=$('#q'),fc=$('#f-cat'),fco=$('#f-country'),ff=$('#f-fund'),so=$('#f-sort'),cnt=$('#count');
  // populate selects
  const cats=STATS.category_labels||{};
  fc.innerHTML='<option value="">All categories</option>'+Object.keys(cats).map(k=>`<option value="${k}">${esc(cats[k])}</option>`).join('');
  const countries=[...new Set(OPPS.map(o=>o.country_main))].sort();
  fco.innerHTML='<option value="">All countries</option>'+countries.map(c=>`<option>${esc(c)}</option>`).join('');
  // preset from ?cat=
  const pre=new URLSearchParams(location.search).get('cat'); if(pre)fc.value=pre;
  function apply(){
    let list=OPPS.slice();
    const t=(q.value||'').toLowerCase().trim();
    if(t)list=list.filter(o=>(o.program+' '+o.organization+' '+o.description+' '+o.country).toLowerCase().includes(t));
    if(fc.value)list=list.filter(o=>o.category===fc.value);
    if(fco.value)list=list.filter(o=>o.country_main===fco.value);
    if(ff.value==='funded')list=list.filter(o=>o.is_funded);
    if(so.value==='deadline')list.sort((a,b)=>(a.deadline_iso||'9999').localeCompare(b.deadline_iso||'9999'));
    else if(so.value==='az')list.sort((a,b)=>a.program.localeCompare(b.program));
    else list.sort((a,b)=>b.score-a.score);
    cnt.textContent=`${list.length} opportunit${list.length===1?'y':'ies'}`;
    render(list,grid);
  }
  [q,fc,fco,ff,so].forEach(el=>{el.addEventListener('input',apply);el.addEventListener('change',apply);});
  apply();
}
document.addEventListener('DOMContentLoaded',boot);
"""


# ─────────────────────────────── HTML ──────────────────────────────────────
_NAV = """<nav class="nav"><div class="container">
  <a class="brand" href="index.html"><span class="logo">A</span> Auriga Career Lab</a>
  <button class="burger" aria-label="menu">&#9776;</button>
  <ul>
    <li><a href="index.html" data-n="home">Home</a></li>
    <li><a href="opportunities.html" data-n="opportunities">Opportunities</a></li>
    <li><a href="categories.html" data-n="categories">Categories</a></li>
    <li><a href="about.html" data-n="about">About</a></li>
    <li><a href="contact.html" data-n="contact">Contact</a></li>
  </ul></div></nav>"""

_FOOTER = """<footer><div class="container">
  <div><strong style="color:#fff">Auriga Career Lab</strong><br>
    <span>Verified fully-funded opportunities for students.</span></div>
  <div class="socials">
    <a href="https://github.com/" target="_blank" rel="noopener">GitHub</a>
    <a href="https://instagram.com/" target="_blank" rel="noopener">Instagram</a>
    <a href="https://facebook.com/" target="_blank" rel="noopener">Facebook</a>
    <a href="https://linkedin.com/" target="_blank" rel="noopener">LinkedIn</a>
  </div></div></footer>"""


def _page(active, body):
    nav = _NAV.replace(f'data-n="{active}"', f'data-n="{active}" class="active"')
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Auriga Career Lab</title>
<meta name="description" content="Verified, fully-funded opportunities for students — scholarships, research, AI/CS, conferences.">
<link rel="stylesheet" href="assets/css/style.css"></head>
<body data-page="{active}">
{nav}
{body}
{_FOOTER}
<script src="assets/js/main.js"></script></body></html>"""


def _index_html():
    return _page("home", """
<header class="hero container">
  <div>
    <div class="eyebrow">Future beyond exams</div>
    <h1>Fully-funded opportunities, verified daily.</h1>
    <p class="sub">Auriga Career Lab finds, verifies and curates scholarships, research
      internships, AI/CS programs and conferences — then shares them as scannable cards.</p>
    <div class="cta">
      <a class="btn primary" href="opportunities.html">Browse opportunities</a>
      <a class="btn ghost" href="categories.html">Explore categories</a>
    </div>
  </div>
  <div class="hero-card"><img id="hero-img" src="assets/images/cards/stem/0_cover.png" alt="Opportunity card preview"></div>
</header>

<section class="block container">
  <h2 class="title">Our mission</h2>
  <p class="lead" style="max-width:760px">Every opportunity here is checked for a live official link,
    an unexpired deadline, full funding and undergraduate eligibility before it reaches you — so
    you can apply with confidence instead of chasing dead links.</p>
</section>

<section class="block container">
  <h2 class="title">Latest opportunities</h2>
  <p class="lead">Freshly verified and added to the catalog.</p>
  <div class="grid" id="latest"></div>
</section>

<section class="block container">
  <h2 class="title">Five categories</h2>
  <p class="lead">Pick a track and dive in.</p>
  <div class="cats">
    <a class="cat-card" href="opportunities.html?cat=stem"><div class="ic">🔬</div><div class="nm">STEM</div><div class="ct"><span data-catcount="stem">0</span> programs</div></a>
    <a class="cat-card" href="opportunities.html?cat=ug_research"><div class="ic">📚</div><div class="nm">UG Research</div><div class="ct"><span data-catcount="ug_research">0</span> programs</div></a>
    <a class="cat-card" href="opportunities.html?cat=ai_cs"><div class="ic">🤖</div><div class="nm">AI / CS</div><div class="ct"><span data-catcount="ai_cs">0</span> programs</div></a>
    <a class="cat-card" href="opportunities.html?cat=scholarships"><div class="ic">🎓</div><div class="nm">Scholarships</div><div class="ct"><span data-catcount="scholarships">0</span> programs</div></a>
    <a class="cat-card" href="opportunities.html?cat=conferences"><div class="ic">🎤</div><div class="nm">Conferences</div><div class="ct"><span data-catcount="conferences">0</span> programs</div></a>
  </div>
</section>

<section class="block container">
  <h2 class="title">Featured programs</h2>
  <p class="lead">Top-tier picks across all tracks.</p>
  <div class="grid" id="featured"></div>
</section>

<section class="block container">
  <h2 class="title">By the numbers</h2>
  <p class="lead">Live snapshot · updated <span id="stat-updated"></span></p>
  <div class="stats">
    <div class="stat"><div class="n" id="stat-total">0</div><div class="l">Opportunities</div></div>
    <div class="stat"><div class="n" id="stat-remaining">0</div><div class="l">Remaining to post</div></div>
    <div class="stat"><div class="n" id="stat-scheduled">0</div><div class="l">Scheduled today</div></div>
    <div class="stat"><div class="n" id="stat-countries">0</div><div class="l">Countries</div></div>
    <div class="stat"><div class="n" id="stat-orgs">0</div><div class="l">Organizations</div></div>
    <div class="stat"><div class="n" id="stat-funded">0</div><div class="l">Funded programs</div></div>
    <div class="stat"><div class="n" id="stat-dbsize">0</div><div class="l">Database size</div></div>
    <div class="stat"><div class="n">100%</div><div class="l">Link-verified</div></div>
  </div>
</section>
""")


def _opportunities_html():
    return _page("opportunities", """
<section class="block container">
  <h2 class="title">All opportunities</h2>
  <p class="lead">Search, filter and sort the full catalog. Every card links to the official page.</p>
  <div class="toolbar">
    <input id="q" type="search" placeholder="Search program, org, country…" autocomplete="off">
    <select id="f-cat"></select>
    <select id="f-country"></select>
    <select id="f-fund"><option value="">All funding</option><option value="funded">Fully funded</option></select>
    <select id="f-sort"><option value="score">Sort: Featured</option><option value="deadline">Sort: Deadline</option><option value="az">Sort: A–Z</option></select>
  </div>
  <p class="count" id="count"></p>
  <div class="grid" id="opps"></div>
</section>
""")


def _categories_html():
    return _page("categories", """
<section class="block container">
  <h2 class="title">Categories</h2>
  <p class="lead">Five tracks. Click any to see its opportunities.</p>
  <div class="cats">
    <a class="cat-card" href="opportunities.html?cat=stem"><div class="ic">🔬</div><div class="nm">STEM</div><div class="ct"><span data-catcount="stem">0</span> programs</div></a>
    <a class="cat-card" href="opportunities.html?cat=ug_research"><div class="ic">📚</div><div class="nm">UG Research</div><div class="ct"><span data-catcount="ug_research">0</span> programs</div></a>
    <a class="cat-card" href="opportunities.html?cat=ai_cs"><div class="ic">🤖</div><div class="nm">AI / CS</div><div class="ct"><span data-catcount="ai_cs">0</span> programs</div></a>
    <a class="cat-card" href="opportunities.html?cat=scholarships"><div class="ic">🎓</div><div class="nm">Scholarships</div><div class="ct"><span data-catcount="scholarships">0</span> programs</div></a>
    <a class="cat-card" href="opportunities.html?cat=conferences"><div class="ic">🎤</div><div class="nm">Conferences</div><div class="ct"><span data-catcount="conferences">0</span> programs</div></a>
  </div>
</section>
""")


def _about_html():
    return _page("about", """
<section class="block container"><div class="prose">
  <h2 class="title">About Auriga Career Lab</h2>
  <p>Auriga Career Lab helps students discover meaningful, fully-funded opportunities beyond the
     usual exam race — and reach them before deadlines close.</p>
  <h2>Mission</h2>
  <p>Make every credible, funded opportunity for students easy to find, trust and act on.</p>
  <h2>Vision</h2>
  <p>A world where a motivated student anywhere can find the right opportunity in minutes,
     not months — and never lose a chance to a dead link or a missed deadline.</p>
  <h2>How opportunities are verified</h2>
  <ul>
    <li>The official URL is fetched live; dead links (4xx/5xx) are rejected.</li>
    <li>Deadlines are checked — anything already expired is dropped.</li>
    <li>Only fully-funded, undergraduate-eligible programs are kept.</li>
    <li>Duplicates are removed by URL canonicalization and content fingerprinting.</li>
  </ul>
  <h2>How rankings work</h2>
  <p>Each opportunity is scored on four factors — <strong>freshness</strong>, <strong>funding</strong>,
     <strong>prestige</strong> and <strong>undergraduate relevance</strong> — and the top picks per
     category are featured first.</p>
  <h2>How often data refreshes</h2>
  <p>The catalog is topped up automatically (self-refilling sources), posts are scheduled daily
     from 7–11 PM, and this site is regenerated on every export run.</p>
</div></section>
""")


def _contact_html():
    return _page("contact", """
<section class="block container"><div class="prose">
  <h2 class="title">Contact</h2>
  <p>Questions, partnerships, or an opportunity to suggest? Reach out.</p>
  <div class="card-panel">
    <form class="form" action="mailto:hello@aurigacareerlab.org" method="post" enctype="text/plain">
      <label for="name">Name</label><input id="name" name="name" required>
      <label for="email">Email</label><input id="email" name="email" type="email" required>
      <label for="msg">Message</label><textarea id="msg" name="message" rows="5" required></textarea>
      <p><button class="btn primary" type="submit">Send</button></p>
    </form>
    <p style="color:#9fb3c8">Or email <a href="mailto:hello@aurigacareerlab.org">hello@aurigacareerlab.org</a></p>
    <div class="socials">
      <a href="https://github.com/" target="_blank" rel="noopener">GitHub</a>
      <a href="https://instagram.com/" target="_blank" rel="noopener">Instagram</a>
      <a href="https://facebook.com/" target="_blank" rel="noopener">Facebook</a>
      <a href="https://linkedin.com/" target="_blank" rel="noopener">LinkedIn</a>
    </div>
  </div>
</div></section>
""")


_README = """# Deploying the Auriga site to GitHub Pages

This `site/` folder is a fully static website (HTML5 + CSS3 + vanilla JS). No build
step, no server. It also hosts the Instagram card images.

## 1. Create a GitHub repository
Create a new repo, e.g. `auriga` (public).

## 2. Push the code
From the `site/` folder:
```bash
cd site
git init
git add .
git commit -m "Auriga static site"
git branch -M main
git remote add origin https://github.com/<username>/<repository>.git
git push -u origin main
```

## 3. Enable GitHub Pages
Repo → **Settings** → **Pages**.

## 4. Select the source
Under **Build and deployment**, set **Source = Deploy from a branch**, choose
**Branch: main**, folder **/(root)**, then **Save**.

## 5. Your site is live
After ~1 minute it is available at:
```
https://<username>.github.io/<repository>/
```

## Hooking up Instagram image hosting
Instagram needs a public image URL. Once deployed, set in your `.env`:
```
IG_IMAGE_BASE_URL=https://<username>.github.io/<repository>
```
The pipeline then builds image URLs as
`IG_IMAGE_BASE_URL/cards/<category>/<file>.png` — which this site serves.

## Local preview
The pages load data with `fetch()`, so open them through a tiny web server (not
file://):
```bash
cd site && python -m http.server 8000   # then visit http://localhost:8000
```

## Updating
Re-run `python main.py --export-site` to regenerate HTML, CSS, JS, JSON, cards and
QR images, then commit & push the `site/` folder again. (Cloudflare Pages works the
same way — point it at this folder.)
"""


# ─────────────────────────────── export ────────────────────────────────────
def export() -> dict:
    site = config.SITE_DIR
    css_dir = site / "assets" / "css"
    js_dir = site / "assets" / "js"
    img_dir = site / "assets" / "images"
    for d in (css_dir, js_dir, img_dir):
        d.mkdir(parents=True, exist_ok=True)

    items, stats = build_data()
    stats["sample_card"] = _copy_cards(img_dir) or "assets/images/cards/stem/0_cover.png"
    _qr_for(items, img_dir / "qr")

    (site / "opportunities.json").write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    (site / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    (css_dir / "style.css").write_text(_CSS, encoding="utf-8")
    (js_dir / "main.js").write_text(_JS, encoding="utf-8")
    (site / "index.html").write_text(_index_html(), encoding="utf-8")
    (site / "opportunities.html").write_text(_opportunities_html(), encoding="utf-8")
    (site / "categories.html").write_text(_categories_html(), encoding="utf-8")
    (site / "about.html").write_text(_about_html(), encoding="utf-8")
    (site / "contact.html").write_text(_contact_html(), encoding="utf-8")
    (site / "README_DEPLOY.md").write_text(_README, encoding="utf-8")

    return {"site_dir": str(site), "opportunities": len(items),
            "images_copied": sum(1 for _ in (img_dir / "cards").rglob("*.png")),
            "qr_generated": sum(1 for _ in (img_dir / "qr").glob("*.png")),
            "index": str(site / "index.html")}
