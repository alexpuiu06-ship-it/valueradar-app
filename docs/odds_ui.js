/* Optional ValueRadar real odds module, no secrets in client browser */
(function(){
'use strict';
function el(id){return document.getElementById(id);}
function esc(x){return String(x==null?'':x).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');}
function pct(x){return x==null||!Number.isFinite(Number(x))?'—':(Number(x)*100).toFixed(1)+'%';}
function matches(){return window.DATA&&Array.isArray(window.DATA.fixtures)?window.DATA.fixtures:[];}
var host=el('message');
if(!host)return;
var panel=document.createElement('div');
panel.innerHTML=[
'<section class="panel" id="odds-module" style="margin-top:16px">',
'<h2>Scanner cote reale — 1X2 pre-match</h2>',
'<div id="odds-status" class="missing">Verific statusul feedului…</div>',
'<div id="odds-list" style="margin-top:10px"></div>',
'<p class="meta">Cotele internaționale nu sunt identice cu ofertele Superbet.ro, Betano.ro, Unibet.ro, MrBit, NetBet România ori Casa Pariurilor. Nicio selecție nu este recomandare de pariere.</p>',
'</section>',
'<section class="panel" id="manual-module" style="margin-top:16px">',
'<h2>Compară manual o cotă de la o casă din România</h2>',
'<p class="meta">Fără abonament: selectezi meciul și introduci cota afișată la casa de pariuri. Sistemul nu plasează pariuri.</p>',
'<div class="controls">',
'<select id="manual-match" aria-label="Meci"><option value="">Se încarcă meciurile…</option></select>',
'<select id="manual-book" aria-label="Bookmaker"><option>Superbet</option><option>Betano</option><option>Unibet</option><option>MrBit</option><option>NetBet</option><option>Casa Pariurilor</option></select>',
'<select id="manual-outcome" aria-label="Selecția"><option value="home">1 — Gazde</option><option value="draw">X — Egal</option><option value="away">2 — Oaspeți</option></select>',
'<input id="manual-price" type="number" step=".01" min="1.01" max="100" placeholder="Cota, ex. 1.95" aria-label="Cota"/>',
'<button id="manual-compare" type="button">Compară</button>',
'</div><div class="missing" id="manual-result">Alege meciul, selecția și cota.</div></section>'
].join('');
host.insertAdjacentElement('afterend',panel);
var review=document.createElement('section');
review.className='panel';
review.style.marginTop='16px';
review.innerHTML='<h2>Evaluarea prețurilor și a avantajului estimat</h2><div id="market-review" class="meta">Se încarcă jurnalul cotelor…</div>';
panel.appendChild(review);
var source=null,watch=null,audit=null;
async function loadJson(path){try{var r=await fetch(path+'?v='+Date.now(),{cache:'no-store'});return r.ok?await r.json():null;}catch(e){return null;}}
async function reload(){var a=await Promise.all([loadJson('./odds_status.json'),loadJson('./odds_watchlist.json'),loadJson('./market_audit.json')]);source=a[0];watch=a[1];audit=a[2];renderOdds();renderMatches();renderAudit();}
function renderOdds(){
 if(!source){el('odds-status').textContent='Nu există date despre scanner; nu se afișează prețuri fictive.';return;}
 var labels={needs_api_key:'Scanner instalat, lipsește cheia API.',connected:'Cote internaționale primite.',partial:'Date parțiale de la furnizor.',no_events:'Nu există evenimente în feed.',api_error:'Eroare de API.',budget_guard:'Limită de credit atinsă.',missing_fixtures:'Lipsesc meciurile de comparat.'};
 el('odds-status').textContent=(labels[source.status]||('Stare: '+source.status))+
 ' Meciuri potrivite: '+(source.matched_games||0)+
 '. Prețuri comparate: '+(source.evaluated_prices||0)+
 '. Credite folosite: '+(source.spent_this_month==null?'—':source.spent_this_month)+
 '. Verificat: '+(source.checked_at?new Date(source.checked_at).toLocaleString('ro-RO'):'—')+'.';
 var items=watch&&Array.isArray(watch.items)?watch.items:[];
 if(!source.checked_at||Date.now()-Date.parse(source.checked_at)>4*3600*1000){el('odds-list').textContent='Nu sunt cote suficient de recente pentru o comparație actuală.';return;}
 if(!items.length){el('odds-list').textContent='Nicio discrepanță de preț recentă în lista de monitorizare.';return;}
 el('odds-list').innerHTML=items.slice(0,12).map(function(v){
  return '<div style="padding:10px 0;border-bottom:1px solid #e1eaed"><b>'+esc(v.home)+' — '+esc(v.away)+'</b> · '+esc(v.league)+
  '<div>'+esc(v.bookmaker)+' (internațional) · '+esc(({home:'1',draw:'X',away:'2'})[v.outcome])+
  ' @ '+esc(v.odds)+' · P(model) '+pct(v.model_probability)+' · EV orientativ '+pct(v.estimated_ev)+
  '</div><div class="meta">Nu este ofertă RO confirmată; diferență nevalidată.</div></div>';
 }).join('');
}
function renderAudit(){
 var e=el('market-review');
 if(!audit){e.textContent='Jurnalul de cote nu este încă disponibil.';return;}
 e.innerHTML='Cote comparate în istoric: <b>'+esc(audit.observations||0)+'</b> · '+
 'Semnale înregistrate prospectiv: <b>'+esc(audit.initial_positive_ev_signals||0)+'</b> · '+
 'Semnale cu rezultat final: <b>'+esc(audit.signals_settled||0)+'</b>'+
 '<div class="meta">Aceasta este o simulare pe hârtie. Nu măsoară pariuri executate la cotele din România. '+
 'Un ROI nu este relevant fără suficient istoric, verificarea cotelor și controlul incertitudinii.</div>';
}
function renderMatches(){
 var fixtures=matches();if(!fixtures.length)return;
 var input=el('manual-match'),old=input.value;
 input.innerHTML=fixtures.slice(0,100).map(function(f,i){return '<option value="'+i+'">'+esc(f.date+' · '+f.home+' — '+f.away)+'</option>';}).join('');
 if(Array.from(input.options).some(function(o){return o.value===old;}))input.value=old;
}
el('manual-compare').addEventListener('click',function(){
 var f=matches()[Number(el('manual-match').value)],odd=Number(el('manual-price').value),outcome=el('manual-outcome').value,book=el('manual-book').value;
 if(!f||!Number.isFinite(odd)||odd<=1.01||odd>100){el('manual-result').textContent='Selectează meciul și introdu o cotă validă între 1,02 și 100.';return;}
 var model=(f.markets||{}).goals;
 if(!model||!model.h2h){el('manual-result').textContent='Nu avem probabilități 1X2 pentru acest meci.';return;}
 var p=Number(model.h2h[outcome]),ev=p*odd-1,limit=1/odd;
 el('manual-result').innerHTML='<b>'+esc(book)+' · '+esc(f.home)+' — '+esc(f.away)+'</b><div>Probabilitate model: '+pct(p)+' · Prag cotă: '+pct(limit)+
 ' · EV matematic: '+pct(ev)+'</div><div class="meta">Model încă nevalidat; cotă introdusă manual și neverificată. Acesta nu este un pariu value confirmat.</div>';
});
reload();setInterval(reload,15*60*1000);setTimeout(renderMatches,3000);
})();
