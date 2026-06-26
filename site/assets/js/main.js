const $=(s,r=document)=>r.querySelector(s);
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
