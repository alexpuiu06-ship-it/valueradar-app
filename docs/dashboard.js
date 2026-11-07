/* Forecasts are hidden whenever the current data cannot be checked. */
'use strict';
window.DATA = null;
(function () {
  const { el, esc, pct, fmt } = window.VR;
  let generation = 0;
  let renderedState = null;
  let operations = null;
  const settlementLabels = { upcoming: 'Așteaptă startul', in_progress: 'Așteaptă încheierea perioadei minime de verificare',
    awaiting_kickoff_evidence: 'Ora exactă de start nu este arhivată',
    awaiting_result: 'Așteaptă rezultat disponibil și neconflictual', awaiting_statistics: 'Așteaptă statistici pentru piață',
    ready_to_settle: 'Rezultat eligibil încă nedecontat', blocked_creation_evidence: 'Momentul predicției nu dovedește pre-match',
    blocked_kickoff_conflict: 'Conflict între ora arhivată și ora rezultatului', settled_with_evidence: 'Decontate cu dovada rezultatului observat',
    settled_timing_unverifiable: 'Momentul decontării nu poate fi validat', settled_result_conflict: 'Rezultatul sursei diferă de cel arhivat',
    settled_evidence_missing: 'Dovada rezultatului lipsește sau este invalidă' };
  const nonnegative = n => Number.isSafeInteger(n) && n >= 0;
  function validOperations() {
    const r = operations, s = r && r.settlement;
    return !!(r && r.schema_version === 1 && r.verified_value === false && r.hypothetical_roi === null &&
      VR.freshness(r.generated_at, 24 * 90).valid && !VR.freshness(r.generated_at, 24 * 90).future &&
      VR.freshness(r.analysis_generated_at, 24 * 90).valid && !VR.freshness(r.analysis_generated_at, 24 * 90).future &&
      r.policy && r.policy.model_warning_after_hours === 6 && r.policy.ro_warning_after_hours === 30 &&
      r.sources && nonnegative(r.sources.successful) && nonnegative(r.sources.total) && r.sources.successful <= r.sources.total &&
      r.ro_history && nonnegative(r.ro_history.records) && nonnegative(r.ro_history.days_observed) && r.ro_history.days_observed <= r.ro_history.records &&
      (r.ro_history.last_observed_at === null || Number.isFinite(VR.timestamp(r.ro_history.last_observed_at)) && !VR.freshness(r.ro_history.last_observed_at, 24 * 90).future) &&
      s && s.verified_value === false && s.operator_settlement_verified === false && s.generated_at === r.analysis_generated_at &&
      s.by_pipeline_version && Array.isArray(s.samples) && s.samples.length <= 10 && s.samples.every(row => row && typeof row.pipeline_version === 'string' && typeof row.home === 'string' && typeof row.away === 'string') && nonnegative(s.overdue_forecasts) &&
      nonnegative(s.unique_fixtures) && nonnegative(s.forecasts) && s.unique_fixtures <= s.forecasts);
  }
  function renderOperationAlerts() {
    const target = el('operations-alerts');
    if (!validOperations()) { target.textContent = 'Raportul operațional este indisponibil sau invalid. Starea automatizării nu este confirmată.'; return; }
    const r = operations, notes = [];
    const age = (Date.now() - VR.timestamp(r.analysis_generated_at)) / 3600e3;
    notes.push(age > 6 ? 'Actualizarea modelului este întârziată: peste 6 ore fără o analiză nouă.' : 'Analiză publicată: ' + VR.dateTime(r.analysis_generated_at) + '.');
    const roTime = VR.timestamp(r.ro_history.last_observed_at);
    notes.push(!Number.isFinite(roTime) ? 'Lipsește o probă RO în istoricul disponibil.' :
      (Date.now() - roTime) / 3600e3 > 30 ? 'Monitorizarea RO este întârziată: peste 30 de ore fără o probă nouă.' :
      'Ultima probă RO: ' + VR.dateTime(r.ro_history.last_observed_at) + '; acoperirea rămâne de verificat.');
    if (r.sources.successful < r.sources.total) notes.push('Surse indisponibile: ' + (r.sources.total - r.sources.successful) + ' din ' + r.sources.total + '.');
    if (r.settlement.overdue_forecasts) notes.push(r.settlement.overdue_forecasts + ' estimări așteaptă rezultate/statistici de peste 48 de ore după perioada minimă de verificare.');
    target.textContent = notes.join(' ');
  }
  function renderOperations() {
    renderOperationAlerts();
    const target = el('settlement-summary');
    if (!validOperations()) { target.textContent = 'Decontările nu pot fi verificate fără raportul operațional.'; return; }
    if (!window.DATA || operations.analysis_generated_at !== DATA.generated_at || operations.pipeline_version !== DATA.pipeline_version) {
      target.textContent = 'Raportul de decontare nu este asociat cu analiza afișată; numărătorile sunt ascunse.'; return;
    }
    const s = operations.settlement, counts = s.by_pipeline_version[DATA.pipeline_version] || {};
    if (Object.entries(counts).some(([state, n]) => !Object.hasOwn(settlementLabels, state) || !nonnegative(n))) {
      target.textContent = 'Numărătorile de decontare sunt invalide.'; return;
    }
    const total = Object.values(counts).reduce((a, b) => a + b, 0);
    const rows = Object.entries(counts).map(([state, n]) => '<tr><td>' + esc(settlementLabels[state]) + '</td><td>' + esc(n) + '</td></tr>').join('');
    const samples = s.samples.filter(row => row.pipeline_version === DATA.pipeline_version).slice(0, 10).map(row => '<tr><td>' +
      esc(row.league + ' · ' + row.date + ' · ' + row.home + ' — ' + row.away) + '</td><td>' + esc(row.market) + '</td><td>' +
      esc(settlementLabels[row.status] || 'Stare necunoscută') + '</td></tr>').join('');
    const source = DATA.pipeline_execution && DATA.pipeline_execution.supplementary_scores;
    const qualifiedSource = source && source.training_use === false && source.value_enabled === false &&
      nonnegative(source.eligible_matches) && nonnegative(source.eligible_forecasts) &&
      source.eligible_matches <= source.eligible_forecasts && source.eligible_forecasts <= (counts.settled_with_evidence || 0);
    const sourceNote = qualifiedSource && source.eligible_matches > 0 ? '<p id="supplementary-scores">Scoruri OddsPapi la 90 de minute: ' +
      esc(source.eligible_matches) + ' meciuri, ' + esc(source.eligible_forecasts) +
      ' estimări evaluate din versiunea curentă. Sunt folosite numai pentru evaluarea predicțiilor arhivate. Eșantionul nu confirmă calibrarea sau profitul; statisticile celorlalte piețe se așteaptă separat.</p>' : '';
    target.innerHTML = '<p id="settlement-current">Versiunea ' + esc(DATA.pipeline_version) + ': <b>' + esc(counts.settled_with_evidence || 0) +
      '</b> estimări decontate cu dovadă din <b>' + esc(total) + '</b>. Numărătorile acoperă toate ligile și piețele acestei versiuni.</p>' +
      '<p class="meta">Jurnalul complet: ' + esc(s.forecasts) + ' estimări din ' + esc(s.unique_fixtures) + ' meciuri distincte. Piețele și versiunile sunt înregistrări separate.</p>' +
      sourceNote + '<details id="settlement-details"><summary>De ce mai sunt estimări în așteptare?</summary><div class="table-scroll"><table><thead><tr><th>Stare</th><th>Estimări</th></tr></thead><tbody>' + rows +
      '</tbody></table></div>' + (samples ? '<h3>Exemple din coadă sau carantină</h3><div class="table-scroll"><table><thead><tr><th>Meci</th><th>Piață</th><th>Motiv</th></tr></thead><tbody>' + samples + '</tbody></table></div>' : '') +
      '<p>Rezultatele conflictuale sunt excluse din scoruri. Predicțiile și decontările deja arhivate rămân neschimbate. Perioada de două ore după start este o protecție operațională, nu o confirmare independentă a finalului meciului.</p></details>';
  }
  function announce() { window.dispatchEvent(new Event('valueradar:datachanged')); }
  function clearData(message) {
    window.DATA = null;
    renderedState = null;
    for (const id of ['history', 'upcoming', 'sources', 'sync']) el(id).textContent = '—';
    el('message').textContent = message;
    el('fixtures').textContent = 'Analizele sunt ascunse până la verificarea unor date proaspete.';
    el('validation').textContent = 'Validarea nu este disponibilă fără un set de date verificabil.';
    el('data-health').textContent = 'Starea datelor este indisponibilă până la o încărcare reușită.';
    renderOperations();
    announce();
  }
  async function load() {
    const current = ++generation;
    operations = null;
    clearData('Se verifică actualizarea…');
    VR.fetchJSON('./operations_report.json').then(report => {
      if (current === generation) { operations = report; renderOperations(); }
    }).catch(() => { if (current === generation) { operations = null; renderOperations(); } });
    try {
      const data = await VR.fetchJSON('./latest.json');
      if (current !== generation) return;
      if (!data || !Array.isArray(data.fixtures) || data.fixtures.some(f => !f || !f.league || !f.home || !f.away || !/^\d{4}-\d{2}-\d{2}$/.test(f.date || '') || !f.markets || typeof f.markets !== 'object')) throw Error('Formatul analizelor este invalid.');
      const state = VR.freshness(data.generated_at);
      if (!state.fresh) throw Error(!state.valid ? 'Lipsește un timestamp valid cu fus orar.' : state.future ? 'Timestamp-ul datelor este în viitor.' : 'Datele au peste 12 ore.');
      window.DATA = data;
      render(); renderOperations(); announce();
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
    const state = JSON.stringify([data.generated_at, league, market, fixtures.map(VR.fixtureId), new Date().toISOString().slice(0, 10)]);
    if (state === renderedState) return false;
    renderedState = state;
    el('history').textContent = data.history_rows || 0;
    el('upcoming').textContent = fixtures.length;
    el('sources').textContent = (data.source_success || 0) + '/' + (data.source_total || 0);
    el('sync').textContent = VR.dateTime(data.generated_at);
    el('message').textContent = 'Model experimental. ' + (data.prospective_predictions_recorded || 0) + ' estimări în jurnal; eligibilitatea pentru evaluare prospectivă se verifică separat. Nu există pariuri value verificate.' +
      (data.source_success < data.source_total ? ' Atenție: unele surse au eșuat; verifică istoricul real al pieței.' : '');
    const failures = (data.source_report || []).filter(x => x.ok !== true);
    const marketNames = { goals: 'Goluri / 1X2', yellow: 'Galbene', corners: 'Cornere', fouls: 'Faulturi' };
    const healthRows = Object.entries(data.last_stat_date || {}).map(([name, dates]) => '<tr><td>' + esc(name) + '</td>' +
      Object.entries(marketNames).map(([key, label]) => {
        const health = data.data_health && data.data_health[name] && data.data_health[name][key];
        return '<td>' + esc(dates[key] || 'fără date') + (health && !health.comparison_allowed ? '<br><b>Comparație blocată</b>' : '') + '</td>';
      }).join('') + '</tr>').join('');
    el('data-health').innerHTML = '<details><summary>Starea datelor pe ligi și piețe</summary><p>O rulare recentă nu garantează statistici recente. Istoricul de peste 21 de zile sau lipsa sursei curente blochează comparațiile. Este o regulă conservatoare, nu un prag validat statistic.</p>' +
      (failures.length ? '<p class="missing">Surse indisponibile: ' + esc(failures.map(x => x.league + ' · ' + ({results:'rezultate curente', fixtures:'program', historical:'istoric'}[x.kind] || x.kind)).join('; ')) + '.</p>' : '<p>Toate sursele au răspuns la ultima verificare.</p>') +
      '<div class="table-scroll"><table><thead><tr><th>Ligă</th>' + Object.values(marketNames).map(x => '<th>' + esc(x) + '</th>').join('') +
      '</tr></thead><tbody>' + healthRows + '</tbody></table></div></details>';
    const items = fixtures.filter(f => league === 'all' || f.league === league);
    el('fixtures').innerHTML = items.length ? items.map(f => {
      const key = market === 'h2h' ? 'goals' : market, p = f.markets[key];
      const valid = VR.marketAvailable(p) && (market === 'h2h' ? VR.distribution(p.h2h) : VR.probability(p.over) && VR.probability(p.under) && Math.abs(p.over + p.under - 1) <= .0001);
      const kickoff = VR.kickoff(f), dateLabel = Number.isFinite(kickoff) ? VR.dateTime(new Date(kickoff).toISOString()) : f.date + ' · ora necunoscută';
      const rejection = f.market_rejections && f.market_rejections[key];
      let body = '<div class="missing">' + esc(p && !VR.marketAvailable(p) ? p.availability && p.availability.message || 'Comparație blocată: istoricul este vechi sau nu poate fi verificat.' : rejection && rejection.message || (p ? 'Probabilități invalide; analiza a fost blocată.' : 'Date insuficiente pentru această piață.')) +
        (rejection ? '<p>Observații disponibile: ligă ' + esc(rejection.n_league) + ' (minim ' + esc(rejection.minimum_league) + '); gazde ' + esc(rejection.n_home) + ', oaspeți ' + esc(rejection.n_away) + ' (minim ' + esc(rejection.minimum_team) + ' fiecare).</p>' : '') + '</div>';
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
    return true;
  }
  el('refresh').addEventListener('click', () => { load(); window.dispatchEvent(new Event('valueradar:refresh')); });
  el('league').addEventListener('change', render);
  el('market').addEventListener('change', render);
  setInterval(() => { if (render()) announce(); renderOperationAlerts(); }, 60e3);
  setInterval(load, 15 * 60e3);
  load();
}());
