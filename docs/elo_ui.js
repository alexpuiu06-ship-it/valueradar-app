/* ValueRadar Elo research comparison. Only display; never change betting choices. */
(function(){
'use strict';
var root=document.getElementById('validation');
if(!root)return;
var panel=document.createElement('section');
panel.className='panel';
panel.style.marginTop='17px';
panel.innerHTML=[
 '<h2>Model alternativ Elo — comparație 1X2</h2>',
 '<p class="meta">Elo urmărește nivelul relativ al echipelor, cu avantaj de teren și actualizare după rezultate. Este un candidat testat separat, NU model aprobat pentru pariuri.</p>',
 '<div id="elo-summary" class="meta">Se încarcă cercetarea Elo…</div>',
 '<div class="controls"><select id="elo-match" aria-label="Alege meciul Elo"><option value="">Aștept meciurile…</option></select></div>',
 '<div id="elo-compare" class="missing">Selectează un meci pentru a compara metodele.</div>',
 '<p class="meta">Când modelele diferă mult, nu presupunem că varianta care oferă cea mai mare cotă teoretică este cea bună. Alegem doar după rezultate din testele istorice și prospective.</p>'
].join('');
root.insertAdjacentElement('afterend',panel);
var report=null;
function el(id){return document.getElementById(id);}
function safe(v){return String(v==null?'':v).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');}
function p(x){return x==null||!Number.isFinite(Number(x))?'—':(Number(x)*100).toFixed(1)+'%';}
function x3(v){return ['home','draw','away'].map(function(k){return (k==='home'?'1':k==='draw'?'X':'2')+': '+p(v&&v[k]);}).join(' · ');}
async function readReport(){
 try{var r=await fetch('./elo_challenger.json?rev='+Date.now(),{cache:'no-store'});
  if(!r.ok)throw Error('Raportul Elo nu a fost publicat.');
  report=await r.json();render();}catch(e){el('elo-summary').textContent=String(e.message);}
}
function render(){
 if(!report)return;
 var audit=report.holdout||{},market=report.market_diagnostic;
 var ci=audit.approx_95_ci||[];
 var hasZero=ci.length===2&&ci[0]<=0&&ci[1]>=0;
 var label=hasZero?'Avantajul pe testul final este neconcludent.':'Intervalul aproximativ sugerează o diferență, dar nu dovedește profit.';
 var text='Model ales pe validare: '+safe(report.best_candidate)+' · Test final: '+safe(audit.n||0)+
 ' meciuri · Îmbunătățire log-loss vs Poisson: '+safe(audit.logloss_gain_vs_current)+' · Interval aproximativ: '+
 (ci.length===2?safe(ci[0]+' … '+ci[1]):'insuficient')+'. '+label;
 if(market&&market.n){
  text+=' Compararea cu o fotografie a cotelor: '+safe(market.n)+' meciuri, abatere maximă medie '+safe(market.mean_largest_gap_pp_current)+
 ' pp pentru modelul actual și '+safe(market.mean_largest_gap_pp_elo)+' pp pentru Elo.';
 }
 el('elo-summary').textContent=text;
 var games=Array.isArray(report.live_research_only)?report.live_research_only:[];
 var input=el('elo-match'),old=input.value;
 input.innerHTML=games.slice(0,250).map(function(x,i){return '<option value="'+i+'">'+
  safe(x.date+' · '+x.league+' · '+x.home+' — '+x.away)+'</option>';}).join('');
 if(Array.from(input.options).some(function(x){return x.value===old;}))input.value=old;
 renderMatch();
}
function renderMatch(){
 if(!report)return;
 var i=Number(el('elo-match').value),games=report.live_research_only||[],x=games[i];
 if(!x){el('elo-compare').textContent='Nu există un meci pentru comparație.';return;}
 var current=(window.DATA&&window.DATA.fixtures||[]).find(function(f){
  return f.league===x.league&&f.date===x.date&&f.home===x.home&&f.away===x.away;});
 var old=current&&current.markets&&current.markets.goals&&current.markets.goals.h2h;
 el('elo-compare').innerHTML='<b>'+safe(x.home)+' — '+safe(x.away)+'</b>'+
 '<div><b>Model actual 1X2:</b> '+x3(old)+'</div>'+
 '<div><b>Candidat Elo 1X2:</b> '+x3(x.probabilities)+'</div>'+
 '<div class="meta">Rating Elo gazde: '+safe(x.rating_home)+' ('+safe(x.games_home)+' meciuri) · oaspeți: '+
 safe(x.rating_away)+' ('+safe(x.games_away)+' meciuri) · avantaj teren inclus în diferență de '+
 safe(x.rating_difference_including_home_advantage)+' puncte Elo.</div>'+
 '<div class="meta">'+(x.low_sample?'Eșantion Elo redus. ':'')+
 'Ambele estimări sunt experimentale. Nu este recomandare de pariere.</div>';
}
el('elo-match').addEventListener('change',renderMatch);
readReport();
setInterval(readReport,3600*1000);
})();