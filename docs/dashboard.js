/* Forecasts are hidden whenever the current data cannot be checked. */
'use strict';
window.DATA = null;
(function () {
  const { el, esc, pct, fmt } = window.VR;
  let generation = 0;
  function announce() { window.dispatchEvent(new Event('valueradar:datachanged')); }
  function clearData(message) {
    window.DATA = null;
    for (const id of ['history', 'upcoming', 'sources', 'sync']) el(id).textContent = '—';
    el('message').textContent = message;
    el('fixtures').textContent = 'Analizele sunt ascunse până la verificarea unor date proaspete.';
    el('validation').textContent = 'Validarea nu este disponibilă fără un set de date verificabil.';
    announce();
  }
  async function load() {
    const current = ++generation;
    clearData('Se verifică actualizarea…');
    try {
      const data = await VR.fetchJSON('./latest.json');
      if (current !== generation) return;
      if (!data || !Array.isArray(data.fixtures) || data.fixtures.some(f => !f || !f.league || !f.home || !f.away || !/^\d{4}-\d{2}-\d{2}$/.test(f.date || '') || !f.markets || typeof f.markets !== 'object')) throw Error('Formatul analizelor este invalid.');
      const state = VR.freshness(data.generated_at);
      if (!state.fresh) throw Error(!state.valid ? 'Lipsește un timestamp valid cu fus orar.' : state.future ? 'Timestamp-ul datelor este în viitor.' : 'Datele au peste 12 ore.');
      window.DATA = data;
      render(); announce();
    } catch (error) {
      if (current === generation) clearData('Comparațiile sunt blocate. ' + error.message + ' Reîncarcă după verificarea fluxului Actions.');
    }
  }
  function explanationView(prediction, market) {
    const e = prediction.explanation;
    if (!e) return '<p class="missing">Lipsește traseul calculului; estimarea nu este verificabilă.</p>';
    const rows = [
      ['Media ligii (gazde)', e.league_home_mean], ['Media ligii (oaspeți)', e.league_away_mean],
      ['Gazde: producție brută', e.home_team_for_mean_raw], ['Oaspeți: permis gazdelor, brut', e.away_opponent_concedes_to_home_raw],
      ['Oaspeți: producție brută', e.away_team_for_mean_raw], ['Gazde: permis oaspeților, brut', e.home_opponent_concedes_to_away_raw],
      ['Atac gazde regularizat', e.home_attack_shrunk], ['Permis gazdelor regularizat', e.opponent_home_conceded_shrunk],
      ['Atac oaspeți regularizat', e.away_attack_shrunk], ['Permis oaspeților regularizat', e.opponent_away_conceded_shrunk],
      ['Lambda gazde', e.predicted_home_mean], ['Lambda oaspeți', e.predicted_away_mean],
      ['Total estimat', e.predicted_total_mean], ['Total mediu al ligii', e.league_total_mean],
      ['Diferență gazde față de ligă', e.home_shift_vs_league], ['Diferență oaspeți față de ligă', e.away_shift_vs_league],
      ['Dispersie folosită', e.dispersion]
    ];
    const distribution = market === 'h2h' ? '1X2: însumăm combinațiile de scor din două distribuții Poisson independente, apoi normalizăm.' :
      'Totaluri: ' + (e.count_distribution === 'negative_binomial' ? 'binomială negativă' : 'Poisson') + '; P(peste L) = 1 − Σ P(N=k), k=0…floor(L).';
    return '<details class="explanation"><summary>Cum a calculat ValueRadar?</summary>' +
      '<p class="meta">Model: ' + esc(e.method_version) + ' · Date strict anterioare ' + esc(e.historical_cutoff_exclusive) +
      '. Istoric efectiv: ' + esc(e.first_observation_date || e.first_historical_date || 'vezi sursele') + ' … ' + esc(e.last_observation_date || e.last_historical_date || 'data-limită de mai sus') + '.</p>' +
      '<p class="meta"><b>Formulele:</b> w = 2^(−vechime/' + esc(e.half_life_days) + '); media ponderată = Σ(w × observație)/Σw; ' +
      'media regularizată = (media brută × Σw + ' + esc(e.prior_pseudogames) + ' × media ligii)/(Σw + ' + esc(e.prior_pseudogames) + '). ' +
      (e.opponent_effect === false ? 'Lambda = atac regularizat.' : 'Lambda gazde = √(atac gazde regularizat × permis gazdelor regularizat); analog pentru oaspeți.') +
      ' Lambda este limitată între 0,05 și 2,4 × media ligii. Total = lambda gazde + lambda oaspeți.</p>' +
      '<div class="table-scroll"><table><tbody>' + rows.map(([label, value]) => '<tr><td>' + esc(label) + '</td><td>' + fmt(value, 4) + '</td></tr>').join('') + '</tbody></table></div>' +
      '<p class="meta">' + esc(distribution) + ' Eșantion brut: ligă ' + esc(prediction.n_league) + ', gazde ' + esc(prediction.n_home) + ', oaspeți ' + esc(prediction.n_away) +
      '. Suma ponderilor: ' + fmt(e.home_team_effective_matches) + ' / ' + fmt(e.away_team_effective_matches) + ' (nu numărul brut de meciuri).</p>' +
      '<p class="meta"><b>Surse folosite:</b> ' + esc((e.source_families || []).join('; ') || 'neprecizate') + '.</p>' +
      '<p class="missing"><b>Incertitudine:</b> ' + esc(e.uncertainty && e.uncertainty.message || 'Nu există un interval de eroare validat pentru probabilitatea acestui meci.') +
      ' Modelul operațional nu are calibrare prospectivă demonstrată. Eșantionul și factorii lipsă pot schimba mult estimarea.</p>' +
      '<p class="meta">Nu intră: arbitru, formații confirmate, accidentări, tactică sau cote RO validate. Acestea sunt etape aritmetice, nu cauze demonstrate. ' +
      '<a href="https://github.com/alexpuiu06-ship-it/valueradar-app/blob/main/ANALYSIS_METHODOLOGY.md">Metodologie și limitări</a></p></details>';
  }
  function render() {
    const data = window.DATA;
    if (!data) return;
    if (!VR.freshness(data.generated_at).fresh) { clearData('Datele nu mai sunt proaspete; comparațiile sunt blocate.'); return; }
    const fixtures = VR.liveFixtures(), league = el('league').value, market = el('market').value;
    el('history').textContent = data.history_rows || 0;
    el('upcoming').textContent = fixtures.length;
    el('sources').textContent = (data.source_success || 0) + '/' + (data.source_total || 0);
    el('sync').textContent = VR.dateTime(data.generated_at);
    el('message').textContent = 'Model experimental. ' + (data.prospective_predictions_recorded || 0) + ' predicții arhivate prospectiv. Nu există pariuri value verificate.' +
      (data.source_success < data.source_total ? ' Atenție: unele surse au eșuat; verifică istoricul real al pieței.' : '');
    const items = fixtures.filter(f => league === 'all' || f.league === league);
    el('fixtures').innerHTML = items.length ? items.map(f => {
      const key = market === 'h2h' ? 'goals' : market, p = f.markets[key];
      const valid = p && (market === 'h2h' ? VR.distribution(p.h2h) : VR.probability(p.over) && VR.probability(p.under) && Math.abs(p.over + p.under - 1) <= .0001);
      const kickoff = VR.kickoff(f), dateLabel = Number.isFinite(kickoff) ? VR.dateTime(new Date(kickoff).toISOString()) : f.date + ' · ora necunoscută';
      const rejection = f.market_rejections && f.market_rejections[key];
      let body = '<div class="missing">' + esc(rejection && rejection.message || (p ? 'Probabilități invalide; analiza a fost blocată.' : 'Date insuficiente pentru această piață.')) + '</div>';
      if (valid) {
        const measures = market === 'h2h' ? VR.x3(p.h2h) : 'Peste ' + p.line + ': ' + pct(p.over) + ' · Sub: ' + pct(p.under) + ' · Medie: ' + fmt(p.mean);
        body = '<div class="metrics"><span class="pill">' + esc(measures) + '</span></div><p class="meta">Observații: ligă ' + esc(p.n_league) + ' · gazde ' + esc(p.n_home) + ' · oaspeți ' + esc(p.n_away) + '</p>' +
          '<div class="missing">' + (p.quality === 'very_low' || p.small_sample ? '<b>Încredere foarte scăzută.</b> Eșantion redus. ' : '') + 'Precizie neconfirmată; nu este un semnal de pariere.</div>' + explanationView(p, market);
      }
      return '<article class="card"><div class="league">' + esc(f.league) + ' · ' + esc(dateLabel) + '</div><h2>' + esc(f.home) + ' — ' + esc(f.away) + '</h2>' + body + '</article>';
    }).join('') : '<div class="panel">Nu sunt meciuri viitoare disponibile în această perioadă.</div>';
    const bt = (data.backtest || {})[market] || {}, pr = (data.prospective || {})[market] || {};
    const version = data.pipeline_version;
    const currentProspective = version && pr.by_pipeline_version && pr.by_pipeline_version[version] || {};
    const currentCount = VR.isNumber(currentProspective.n) && currentProspective.n >= 0 ? currentProspective.n : 0;
    const otherCount = VR.isNumber(pr.n) ? Math.max(0, pr.n - currentCount) : 0;
    const dateKey = market === 'h2h' ? 'goals' : market, last = data.last_stat_date || {};
    const dates = (league === 'all' ? Object.values(last).map(x => x[dateKey]) : [last[league] && last[league][dateKey]]).filter(Boolean).sort();
    const note = bt.n >= 20 ? 'Test cronologic: ' + bt.n + ' predicții; Brier model ' + fmt(bt.brier, 5) + ' vs. reper ' + fmt(bt.baseline_brier, 5) + '; log-loss ' + fmt(bt.log_loss, 5) +
      '. Interval aproximativ al câștigului Brier: ' + VR.interval(bt.improvement_approx_95_range) + '. ' + VR.intervalVerdict(bt.improvement_approx_95_range) : 'Rezultate insuficiente pentru evaluare.';
    el('validation').innerHTML = '<h2>Calibrare și validare</h2><p>' + esc(note) + '</p><p class="meta">' +
      (league === 'all' ? 'Cea mai recentă partidă dintre ligi' : 'Ultima partidă cu statistici în ligă') + ': ' + esc(dates.at(-1) || 'necunoscută') +
      '. Prospețimea poate diferi între ligi. ' + (league !== 'all' ? 'Scorurile de mai sus sunt agregate pe toate ligile; vezi defalcarea de mai jos și raportul de cercetare.' : '') + '</p>' +
      '<p class="meta">Eșantioane de test pe ligi: ' + esc(Object.entries(bt.per_league || {}).map(([k, v]) => k + ': ' + (typeof v === 'number' ? v : v.n || 0)).join(' · ')) + '.</p>' +
      ((bt.bins || []).length ? '<div class="table-scroll"><table><thead><tr><th>Grupă</th><th>N</th><th>Medie estimată</th><th>Frecvență observată</th></tr></thead><tbody>' + bt.bins.map(x => '<tr><td>' + esc(x.range) + '</td><td>' + esc(x.n) + '</td><td>' + pct(x.predicted) + '</td><td>' + pct(x.observed) + '</td></tr>').join('') + '</tbody></table></div>' : '') +
      '<p class="meta" id="prospective-current">Versiunea curentă ' + esc(version || 'neidentificată') + ': predicții prospective decontate ' + esc(currentCount) + '; Brier ' +
      fmt(currentCount ? currentProspective.brier : null, 5) + '. Alte versiuni în jurnal: ' + esc(otherCount) + ' decontări. Agregatul tuturor versiunilor este doar descriptiv și nu validează modelul corectat. ' +
      'Scor mai mic = mai bun. Testul retrospectiv este exploratoriu și nu demonstrează profit sau eroarea exactă a unui meci.</p>';
  }
  el('refresh').addEventListener('click', () => { load(); window.dispatchEvent(new Event('valueradar:refresh')); });
  el('league').addEventListener('change', render);
  el('market').addEventListener('change', render);
  setInterval(() => { render(); announce(); }, 60e3);
  setInterval(load, 15 * 60e3);
  load();
}());
