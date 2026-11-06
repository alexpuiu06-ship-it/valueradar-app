/* ValueRadar research laboratory. No betting recommendations. */
(function(){
'use strict';
var parent=document.getElementById('validation');
if(!parent)return;
var section=document.createElement('section');
section.className='panel';
section.style.marginTop='18px';
section.innerHTML=[
 '<h2>Laborator de modele — ce merită schimbat?</h2>',
 '<p class="meta">Comparam recența, regularizarea și influența adversarului. Variantele sunt alese pe setul de validare și verificate ulterior pe un set cronologic separat. Nicio schimbare nu se aplică automat modelului operațional.</p>',
 '<div id="model-lab-report" class="meta">Se încarcă rezultatele laboratorului…</div>',
 '<details style="margin-top:12px"><summary style="cursor:pointer;font-weight:650">Cum este realizat experimentul?</summary>',
 '<p class="meta">Fiecare campionat este ordonat cronologic: începutul istoricului pentru formare, următoarele 23% pentru comparația variantelor, ultimele 22% pentru testul final. La fiecare meci modelul poate folosi doar datele precedente.</p>',
 '<p class="meta">Comparam: configurația actuală (185 zile, prior 7, adversar inclus); 90 zile; prior 15; și o variantă fără influența adversarului. Indicatorii: Brier și log-loss (mai mici sunt mai buni). Un rezultat bun în istoric nu dovedește profit la pariuri.</p>',
 '</details>'
].join('');
parent.insertAdjacentElement('afterend',section);
function safe(x){return String(x==null?'':x).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');}
async function render(){
 var el=document.getElementById('model-lab-report');
 try{
  var r=await fetch('./model_lab.json?rev='+Date.now(),{cache:'no-store'});
  if(!r.ok)throw new Error('Experimentul nu a fost executat.');
  var data=await r.json();
  var names={h2h:'Rezultat 1X2',yellow:'Cartonașe',corners:'Cornere',goals:'Goluri',fouls:'Faulturi'};
  var variants={current_v1:'Actual',recent_90d:'Recență 90 zile',regularized_15:'Prior 15',team_only:'Fără adversar'};
  var rows=Object.entries(data.markets||{}).map(function(pair){
   var k=pair[0],v=pair[1],choice=v.selected_on_validation;
   var original=v.holdout&&v.holdout.current_v1;
   var alternative=v.holdout&&v.holdout[choice];
   var n=original&&original.n||0;
   var label=choice?variants[choice]||choice:'Date insuficiente';
   var score=original&&original.log_loss!=null?Number(original.log_loss).toFixed(3):'—';
   var altScore=alternative&&alternative.log_loss!=null?Number(alternative.log_loss).toFixed(3):'—';
   var gain=v.holdout_logloss_gain_vs_current;
   var bounds=v.holdout_approx_95_gain_interval;
   var interval=bounds&&bounds.length===2?'['+Number(bounds[0]).toFixed(4)+', '+Number(bounds[1]).toFixed(4)+']':'—';
   var uncertain=bounds&&bounds.length===2&&bounds[0]<=0&&bounds[1]>=0;
   var verdict=!bounds?'Prea puține date':uncertain?'Neconcludent':'Semnal statistic preliminar';
   return '<tr><td>'+safe(names[k]||k)+'</td><td>'+safe(n)+'</td><td>'+safe(label)+'</td>'+
    '<td>'+safe(score)+'</td><td>'+safe(altScore)+'</td><td>'+safe(gain==null?'—':Number(gain).toFixed(4))+'</td>'+
    '<td>'+safe(interval)+'</td><td>'+safe(verdict)+'</td></tr>';
  }).join('');
  var when=data.generated_at?new Date(data.generated_at).toLocaleString('ro-RO'):'neconfirmată';
  el.innerHTML='<div style="overflow:auto"><table style="width:100%;font-size:12px;text-align:left;border-collapse:collapse"><thead><tr>'+
   '<th>Piață</th><th>Teste finale</th><th>Variantă aleasă la validare</th><th>Log-loss actual</th><th>Log-loss challenger</th><th>Diferență</th><th>Interval aprox. 95%</th><th>Interpretare</th>'+
   '</tr></thead><tbody>'+rows+'</tbody></table></div>'+
   '<p class="meta">Raport generat: '+safe(when)+
   '. Diferența pozitivă favorizează challengerul, negativă favorizează modelul actual. Intervalele sunt aproximative și nu corectează dependențele dintre meciuri. Nicio variantă nu este aprobată automat.</p>';
 }catch(error){el.textContent='Laboratorul nu are încă un raport publicat: '+error.message;}
}
render();
setInterval(render,60*60*1000);
})();