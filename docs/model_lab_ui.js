/* Research reports do not modify production probabilities. */
(function () {
  'use strict';
  const { el, esc, fmt } = window.VR;
  const section = document.createElement('section');
  section.className = 'panel';
  section.innerHTML = '<h2>Laborator de modele — ce merită schimbat?</h2><p class="meta">Cercetare retrospectivă: selecția variantelor și calibrarea se fac înaintea testului final. Nicio schimbare nu se aplică automat.</p><div id="model-lab-report">Se încarcă laboratorul…</div><h3>Poisson, Elo și ensemble calibrat</h3><div id="calibration-report">Se încarcă raportul de calibrare…</div>';
  el('validation').insertAdjacentElement('afterend', section);
  const names = { h2h: 'Rezultat 1X2', yellow: 'Galbene', corners: 'Cornere', goals: 'Goluri', fouls: 'Faulturi' };
  const models = { poisson: 'Poisson actual', elo: 'Elo', ensemble: 'Ensemble', poisson_calibrated: 'Poisson calibrat', elo_calibrated: 'Elo calibrat', ensemble_calibrated: 'Ensemble calibrat', league_frequency: 'Frecvențe ligă' };
  let generation = 0;
  async function render() {
    const current = ++generation;
    el('model-lab-report').textContent = 'Se verifică raportul istoric…';
    el('calibration-report').textContent = 'Se verifică raportul de calibrare…';
    await Promise.all([readLab(current), readCalibration(current)]);
  }
  async function readLab(current) {
    try {
      const data = await VR.fetchJSON('./model_lab.json');
      if (current !== generation) return;
      if (!data || !data.markets || !VR.freshness(data.generated_at, Infinity).fresh) throw Error('Raport sau timestamp invalid.');
      const rows = Object.entries(data.markets).map(([market, result]) => {
        const chosen = result.selected_on_validation, original = result.holdout && result.holdout.current_v1 || {}, alternative = result.holdout && result.holdout[chosen] || {};
        return '<tr><td>' + esc(names[market] || market) + '</td><td>' + esc(original.n || 0) + '</td><td>' + esc(chosen || 'date insuficiente') + '</td><td>' + fmt(original.log_loss, 5) +
          '</td><td>' + fmt(alternative.log_loss, 5) + '</td><td>' + esc(VR.interval(result.holdout_approx_95_gain_interval)) + '</td><td>' + esc(VR.intervalVerdict(result.holdout_approx_95_gain_interval)) + '</td></tr>';
      }).join('');
      el('model-lab-report').innerHTML = '<div class="table-scroll"><table><thead><tr><th>Piață</th><th>N final</th><th>Ales pe validare</th><th>Log-loss actual</th><th>Log-loss candidat</th><th>Interval 95% câștig</th><th>Interpretare</th></tr></thead><tbody>' + rows +
        '</tbody></table></div><p class="meta">Raport istoric: ' + esc(VR.dateTime(data.generated_at)) + '. Versiunea datelor: ' + esc(data.protocol && data.protocol.model_pipeline_version || data.input_audit && data.input_audit.model_pipeline_version || 'necunoscută') + '. Câștig pozitiv favorizează candidatul. Scor mai mic este mai bun; rezultatele nu reprezintă ROI. Istoricul a fost analizat anterior: evaluarea rămâne exploratorie, nu un test confirmatoriu pe date complet noi.</p>';
    } catch (error) { if (current === generation) el('model-lab-report').textContent = 'Laborator indisponibil: ' + error.message; }
  }
  function metricsRows(records) {
    return Object.entries(records || {}).map(([name, score]) => '<tr><td>' + esc(models[name] || name) + '</td><td>' + esc(score.n || 0) + '</td><td>' + fmt(score.log_loss, 5) +
      '<br><small>95% ' + esc(VR.interval(score.log_loss_approx_95_range)) + '</small></td><td>' + fmt(score.brier, 5) +
      '<br><small>95% ' + esc(VR.interval(score.brier_approx_95_range)) + '</small></td><td>' + fmt(score.ece, 5) + '</td></tr>').join('');
  }
  function metricsTable(records) {
    return '<div class="table-scroll"><table><thead><tr><th>Model</th><th>N</th><th>Log-loss</th><th>Brier</th><th>ECE</th></tr></thead><tbody>' + metricsRows(records) + '</tbody></table></div>';
  }
  function calibrationBins(records) {
    return '<details><summary>Calibrarea pe grupe de probabilitate</summary><p class="meta">Frecvențele observate nu sunt probabilități perfecte. Intervalele Wilson ale frecvenței presupun observații independente și sunt descriptive.</p>' +
      Object.entries(records || {}).filter(([, score]) => Array.isArray(score.bins) && score.bins.length).map(([name, score]) => '<details><summary>' + esc(models[name] || name) + '</summary><div class="table-scroll"><table><thead><tr><th>Rezultat</th><th>Grupă</th><th>N</th><th>Estimat</th><th>Observat</th><th>Interval 95% frecvență</th></tr></thead><tbody>' +
        score.bins.map(bin => '<tr><td>' + esc(({ home: '1', draw: 'X', away: '2' })[bin.outcome] || bin.outcome) + '</td><td>' + esc(bin.range) + '</td><td>' + esc(bin.n) + '</td><td>' +
          VR.pct(bin.predicted) + '</td><td>' + VR.pct(bin.observed) + '</td><td>' + esc(VR.interval(bin.observed_approx_95_wilson)) + '</td></tr>').join('') + '</tbody></table></div></details>').join('') + '</details>';
  }
  async function readCalibration(current) {
    try {
      const data = await VR.fetchJSON('./calibration_report.json');
      if (current !== generation) return;
      if (!data || !data.holdout || !data.holdout.models || !VR.freshness(data.generated_at, Infinity).fresh) throw Error('Raport sau timestamp invalid.');
      const holdout = data.holdout, selected = data.selected || {}, protocol = data.protocol || {}, dates = protocol.split_dates || {};
      const leagueRows = Object.entries(holdout.by_league || {}).map(([league, group]) => '<details><summary>' + esc(league) + ' · N=' + esc(group.n || 0) + '</summary>' + metricsTable(group.models) + calibrationBins(group.models) + '</details>').join('');
      const gains = Object.entries(holdout.gains_vs_poisson || {}).map(([name, score]) => '<li>' + esc(models[name] || name) + ': câștig log-loss ' + fmt(score.mean_logloss_gain, 5) +
        ', interval 95% ' + esc(VR.interval(score.approx_95_ci)) + ' pe ' + esc(score.blocks || 0) + ' blocuri. ' + esc(VR.intervalVerdict(score.approx_95_ci)) + '</li>').join('');
      el('calibration-report').innerHTML = '<p>Versiunea raportului: ' + esc(protocol.model_pipeline_version || 'necunoscută') + '. Modelul operațional rămâne experimental. Calibrarea candidaților este cercetare, fără promovare automată.</p><p class="missing">Istoricul a fost analizat anterior. Acesta este un studiu exploratoriu, nu o dovadă confirmatorie pe un set complet nou.</p>' + metricsTable(holdout.models) + calibrationBins(holdout.models) +
        '<p class="meta">Elo ales: ' + esc(selected.elo_candidate) + '; pondere Poisson în ensemble: ' + fmt(selected.ensemble_poisson_weight) +
        '. Temperaturile: ' + esc(JSON.stringify(selected.temperatures || {})) + '. ECE măsoară abaterea în grupe și depinde de eșantion; nu este eroarea exactă a unui meci.</p>' +
        '<p class="meta">Validare din ' + esc(dates.validation_start) + '; calibrare din ' + esc(dates.calibration_start) + '; test final din ' + esc(dates.holdout_start) +
        '. Ferestre globale după zile: 55% formare, 15% selecție, 10% calibrare, 20% evaluare; nicio zi nu traversează ferestrele. Fiecare estimare folosește numai meciuri anterioare.</p>' +
        (gains ? '<ul>' + gains + '</ul>' : '') + leagueRows + '<p class="meta">Reper cote no-vig: ' +
        (data.market_baseline && data.market_baseline.status !== 'unavailable' ? esc(data.market_baseline.status) : 'indisponibil — lipsesc cote istorice complete și sincronizate, verificate înainte de start și aliniate cu rezultate prospective') +
        '. Intervalele scorurilor și ale câștigurilor folosesc bootstrap pe săptămâni ISO; nu elimină toate dependențele dintre meciuri. Raport: ' + esc(VR.dateTime(data.generated_at)) + '.</p>';
    } catch (error) { if (current === generation) el('calibration-report').textContent = 'Raport de calibrare indisponibil: ' + error.message + ' Nu se presupune un câștig de precizie.'; }
  }
  window.addEventListener('valueradar:refresh', render);
  render(); setInterval(render, 3600e3);
}());
