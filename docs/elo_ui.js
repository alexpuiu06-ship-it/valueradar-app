/* Elo remains a research candidate, never an executable betting signal. */
(function () {
  'use strict';
  const { el, esc, fmt } = window.VR;
  const panel = document.createElement('section');
  panel.className = 'panel';
  panel.innerHTML = '<h2>Model alternativ Elo — comparație 1X2</h2><p class="meta">Elo actualizează nivelul relativ după rezultatele din fiecare zi. Selecția candidatului precedă testul final.</p><div id="elo-summary">Se încarcă cercetarea Elo…</div><div class="controls"><select id="elo-match" aria-label="Alege meciul Elo" disabled><option value="">Aștept meciurile…</option></select></div><div id="elo-compare" class="missing">Comparația necesită date proaspete din ambele modele.</div>';
  el('validation').insertAdjacentElement('afterend', panel);
  let report = null, generation = 0;
  const games = new Map();
  async function readReport() {
    const current = ++generation;
    report = null; renderMatchList();
    el('elo-summary').textContent = 'Se verifică raportul istoric Elo…';
    try {
      const data = await VR.fetchJSON('./elo_challenger.json');
      if (current !== generation) return;
      if (!data || !data.holdout || !Array.isArray(data.live_research_only) || !VR.freshness(data.generated_at, Infinity).fresh) throw Error('Raport sau timestamp invalid.');
      report = data;
      const holdout = report.holdout;
      el('elo-summary').textContent = 'Candidat ales pe validare: ' + (report.best_candidate || 'date insuficiente') + ' · N test final: ' + (holdout.n || 0) +
        ' · Câștig log-loss față de Poisson: ' + fmt(holdout.logloss_gain_vs_current, 5) + ' · Interval aproximativ 95%: ' + VR.interval(holdout.approx_95_ci) + '. ' +
        VR.intervalVerdict(holdout.approx_95_ci) + ' Raport istoric: ' + VR.dateTime(report.generated_at) + '. Nu dovedește profit.';
      renderMatchList();
    } catch (error) { if (current === generation) el('elo-summary').textContent = 'Raport Elo indisponibil: ' + error.message; }
  }
  function renderMatchList() {
    const select = el('elo-match'), old = select.value;
    games.clear();
    // A valid historical score does not make an old live forecast fresh.
    if (report && VR.freshness(report.generated_at).fresh) for (const f of VR.liveFixtures()) {
      const match = report.live_research_only.find(x => VR.fixtureId(x) === VR.fixtureId(f));
      if (match && VR.distribution(match.probabilities)) games.set(VR.fixtureId(f), { research: match, current: f });
    }
    select.innerHTML = '<option value="">Alege un meci…</option>' + Array.from(games.entries()).map(([id, pair]) => '<option value="' + esc(id) + '">' + esc(pair.current.date + ' · ' + pair.current.home + ' — ' + pair.current.away) + '</option>').join('');
    if (games.has(old)) select.value = old;
    select.disabled = games.size === 0;
    renderMatch();
  }
  function renderMatch() {
    const pair = games.get(el('elo-match').value);
    if (!pair || !window.DATA || !VR.freshness(window.DATA.generated_at).fresh || !VR.upcoming(pair.current)) {
      el('elo-compare').textContent = 'Selectează un meci cu date proaspete din ambele modele. Un raport istoric nu reprezintă o predicție actuală.'; return;
    }
    const x = pair.research, p = pair.current.markets.goals;
    el('elo-compare').innerHTML = '<b>' + esc(x.home) + ' — ' + esc(x.away) + '</b><div>Poisson actual: ' + esc(VR.x3(p && p.h2h)) + '</div><div>Candidat Elo: ' + esc(VR.x3(x.probabilities)) +
      '</div><div class="meta">Rating gazde ' + fmt(x.rating_home, 1) + ' (' + esc(x.games_home) + ' meciuri); oaspeți ' + fmt(x.rating_away, 1) + ' (' + esc(x.games_away) + ' meciuri). ' +
      (x.low_sample ? 'Eșantion Elo redus. ' : '') + 'Avantaj teren inclus: diferență ' + fmt(x.rating_difference_including_home_advantage, 1) + ' puncte. Ambele metode sunt experimentale; nu este un semnal de pariere.</div>';
  }
  el('elo-match').addEventListener('change', renderMatch);
  window.addEventListener('valueradar:datachanged', renderMatchList);
  window.addEventListener('valueradar:refresh', readReport);
  readReport(); setInterval(readReport, 3600e3);
}());
