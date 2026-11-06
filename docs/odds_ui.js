/* Quotes are diagnostic observations. This client has no verified-value capability. */
(function () {
  'use strict';
  const { el, esc, pct } = window.VR;
  const panel = document.createElement('div');
  panel.innerHTML = `
    <section class="panel" id="odds-module"><h2>Scanner cote reale — 1X2 pre-match</h2>
      <div id="odds-status" class="missing" role="status">Verific statusul feedului…</div>
      <p id="odds-list"><b>Nu există pariuri value verificate.</b></p>
      <p class="meta">Cotele internaționale nu confirmă oferte Superbet RO, Betano RO, Unibet RO, MrBit RO, NetBet RO ori Casa Pariurilor. Nicio selecție nu este recomandare de pariere.</p>
    </section>
    <section class="panel" id="ro-feed-module"><h2>Probe de acoperire RO — Superbet și NetBet</h2>
      <div id="ro-feed-status" class="meta" role="status">Se încarcă diagnosticul RO…</div>
      <div id="ro-feed-coverage"></div>
      <p class="meta">Fotografii de diagnostic, fără cote afișate. Numerele arată verificări tehnice la momentul probei, nu oferte actuale confirmate la operator. Absența din răspunsul filtrat nu dovedește lipsa acoperirii furnizorului. Nu există pariuri value verificate.</p>
    </section>
    <section class="panel" id="manual-module"><h2>Compară manual o cotă de la o casă din România</h2>
      <p class="meta">Comparație aritmetică orientativă. Alegerea unui operator nu verifică oferta. Piața 1X2 trebuie să fie rezultatul la 90 de minute plus prelungirile arbitrului, fără reprize suplimentare.</p>
      <div class="controls">
        <select id="manual-match" aria-label="Meci"><option value="">Aștept date proaspete…</option></select>
        <select id="manual-book" aria-label="Bookmaker"><option>Superbet</option><option>Betano</option><option>Unibet</option><option>MrBit</option><option>NetBet</option><option>Casa Pariurilor</option></select>
        <select id="manual-market" aria-label="Piața"><option value="h2h">Rezultat 1X2</option><option value="goals">Total goluri 2,5</option><option value="yellow">Total galbene 4,5</option><option value="corners">Total cornere 9,5</option><option value="fouls">Total faulturi 23,5</option></select>
        <select id="manual-outcome" aria-label="Selecția"><option value="home">1 — Gazde</option><option value="draw">X — Egal</option><option value="away">2 — Oaspeți</option></select>
        <input id="manual-price" type="number" step=".01" min="1.02" max="100" placeholder="Cota, ex. 1.95" aria-label="Cota">
        <button id="manual-compare" type="button" disabled>Compară</button>
      </div><p id="manual-line" class="meta">Aceeași piață, aceeași linie și aceleași reguli sunt obligatorii.</p>
      <div class="missing" id="manual-result" role="status" aria-live="polite">Alege meciul, selecția și cota.</div>
    </section>
    <section class="panel"><h2>Evaluarea prețurilor și a avantajului estimat</h2><div id="market-review" class="meta">Se încarcă jurnalul cotelor…</div></section>`;
  el('message').insertAdjacentElement('afterend', panel);
  let source = null, audit = null, checks = null, roCoverage = null, generation = 0;
  const manualGames = new Map();
  async function safeRead(path) { try { return await VR.fetchJSON(path); } catch (_) { return null; } }
  async function reload() {
    const current = ++generation;
    source = audit = checks = roCoverage = null;
    renderOdds(); renderAudit(); renderRO();
    const results = await Promise.all([safeRead('./odds_status.json'), safeRead('./market_audit.json'), safeRead('./odds_diagnostics.json'), safeRead('./ro_feed_status.json')]);
    if (current !== generation) return;
    [source, audit, checks, roCoverage] = results;
    renderOdds(); renderAudit(); renderRO();
  }
  function renderRO() {
    const status = el('ro-feed-status'), table = el('ro-feed-coverage'), report = roCoverage;
    table.replaceChildren();
    const stamp = report && VR.freshness(report.generated_at, 24);
    const leagues = ['Premier League', 'La Liga', 'Serie A', 'Bundesliga', 'Ligue 1'];
    const valid = report && report.schema_version === 1 && report.provider === 'PropLine' &&
      report.verified_value === false && report.operator_prices_independently_verified === false && report.raw_odds_saved === false &&
      report.max_quote_age_seconds === 120 && Array.isArray(report.leagues) && report.leagues.length === 5 &&
      new Set(report.leagues.map(row => row && row.league)).size === 5 && report.leagues.every(row => row && leagues.includes(row.league)) &&
      Number.isFinite(Date.parse(report.generated_at)) && Date.parse(report.generated_at) <= Date.now() + 5 * 60e3;
    if (!valid) { status.textContent = 'Diagnosticul RO este indisponibil sau invalid. Nu se confirmă oferte ori semnale value.'; return; }
    status.textContent = 'Ultima probă: ' + VR.dateTime(report.generated_at) + '. ' +
      (stamp.fresh ? 'Fotografie istorică; verificare zilnică programată.' : 'Diagnosticul are peste 24 de ore sau un timestamp invalid; acoperirea actuală este necunoscută.') +
      ' Pragul local de prospețime al fiecărei cote: 120 secunde la primirea răspunsului.';
    const reasons = { stale_market_timestamp: 'timestamp de piață vechi', stale_selection_timestamp: 'selecție veche',
      fixture_identity_or_kickoff_not_matched: 'identitate sau oră diferită', unsupported_selection_identity: 'selecție neidentificată',
      already_started: 'meci început', model_history_not_current: 'istoric al modelului neactualizat' };
    const states = { needs_api_key: 'cheie neconfigurată', provider_error: 'eroare de furnizor', stale_analysis: 'model vechi',
      invalid_schema: 'format invalid', diagnostic_error: 'eroare de diagnostic' };
    const count = value => Number.isSafeInteger(value) && value >= 0;
    const rows = report.leagues.map(row => {
      const quality = row.quality;
      const cells = ['superbet_ro', 'netbet_ro'].map(book => {
        const diag = quality && quality.book_diagnostics && quality.book_diagnostics[book];
        if (!diag || !count(diag.received_blocks) || !count(diag.complete_recent_markets) || !count(diag.matched_current_model_markets) ||
            diag.matched_current_model_markets > diag.complete_recent_markets || diag.complete_recent_markets > diag.received_blocks) return '<td>—</td>';
        return '<td>' + esc(diag.complete_recent_markets) + ' / ' + esc(diag.matched_current_model_markets) +
          (diag.received_blocks === 0 ? '<br><span class="meta">absent din răspuns</span>' : '') + '</td>';
      }).join('');
      const details = quality && quality.rejection_counts && typeof quality.rejection_counts === 'object' ?
        Object.entries(quality.rejection_counts).filter(([, n]) => count(n) && n > 0).map(([reason, n]) => (reasons[reason] || reason) + ': ' + n).join('; ') : '';
      return '<tr><td>' + esc(row.league) + '<br><span class="meta">' + esc(VR.dateTime(row.received_at)) +
        ' · filtru livrare: ' + esc(row.requested_max_delivery_age_seconds) + ' s</span></td>' + cells +
        '<td>' + esc(states[row.status] || details || 'Nicio respingere raportată în această probă.') + '</td></tr>';
    }).join('');
    table.innerHTML = '<p class="meta">Fiecare celulă: piețe 1X2 complete și recente / potrivite cu modelul. Aceste numere nu măsoară toată oferta operatorului.</p>' +
      '<div class="table-scroll"><table><thead><tr><th>Ligă · probă</th><th>Superbet RO</th><th>NetBet RO</th><th>Respingere / eroare</th></tr></thead><tbody>' + rows + '</tbody></table></div>';
  }
  function renderOdds() {
    el('odds-list').textContent = 'Nu există pariuri value verificate. Lipsesc cotele RO confirmate și validarea prospectivă a modelului.';
    if (!source) { el('odds-status').textContent = 'Statusul feedului este indisponibil sau cererea a expirat. Cotele nu pot fi verificate.'; return; }
    const labels = { needs_api_key: 'Scannerul nu a efectuat cereri: lipsește cheia API.', connected: 'Cote internaționale primite.', partial: 'Feed internațional parțial.', no_events: 'Niciun eveniment în feed.', no_valid_quotes: 'Nicio cotă acceptată: evenimentele au fost respinse la verificare.', api_error: 'Eroare de API.', budget_guard: 'Protecție de buget: nu s-au solicitat cote.', missing_fixtures: 'Lipsesc meciurile.', stale_model: 'Model prea vechi pentru compararea cotelor.', budget_invalid: 'Buget invalid: nu s-au solicitat cote.' };
    // An attempt timestamp proves only that the scanner ran, never price freshness.
    const stamp = source.data_timestamp || source.last_successful_quote_at;
    const fresh = VR.freshness(stamp, 2);
    const prefix = labels[source.status] || 'Starea feedului: ' + String(source.status || 'necunoscută');
    el('odds-status').textContent = prefix + ' Ultima încercare: ' + VR.dateTime(source.attempted_at || source.checked_at) +
      '. Timestamp cote acceptate: ' + VR.dateTime(stamp) + '. ' + (!fresh.fresh ? 'Cotele sunt vechi, lipsesc sau au un timestamp invalid; nu sunt o comparație actuală. ' : '') +
      'Meciuri potrivite: ' + (source.matched_games || 0) + '. Prețuri comparate: ' + (source.evaluated_prices || 0) + '. Credite rezervate conservator în luna curentă: ' + (source.spent_this_month == null ? 'necunoscut' : source.spent_this_month) + '.';
  }
  function renderAudit() {
    const review = el('market-review');
    if (!audit) { review.textContent = 'Jurnalul de cote nu este disponibil. Nu există pariuri value verificate.'; return; }
    review.innerHTML = 'Comparații istorice: <b>' + esc(audit.observations || 0) + '</b> · Diferențe matematice nevalidate: <b>' +
      esc(audit.unverified_model_price_differences || 0) + '</b>.<p>Nu există pariuri value verificate. Profitul și ROI nu sunt validate și nu se afișează.</p>';
    if (!checks || !Array.isArray(checks.items)) { review.innerHTML += '<p class="meta">Diagnosticul consensului este indisponibil.</p>'; return; }
    const stamp = checks.data_timestamp || checks.generated_at;
    const fresh = VR.freshness(stamp, 2);
    const rows = checks.items.slice(0, 8).map(row => '<tr><td>' + esc(row.league) + ' · ' + esc(row.home) + ' — ' + esc(row.away) + '</td><td>' +
      esc(row.books) + '</td><td>' + esc(row.max_model_consensus_gap_pp) + ' pp</td><td>' + esc(VR.x3(row.model_probabilities)) + '<br>' + esc(VR.x3(row.market_consensus_no_vig)) + '</td></tr>').join('');
    review.innerHTML += '<h3>Diferențe model–piață în observațiile salvate</h3><p class="meta">Fotografie istorică: ' + esc(VR.dateTime(stamp)) +
      '. ' + (fresh.fresh ? '' : '<b>Nu reprezintă cote actuale.</b> ') + 'Probabilitățile modelului provin din scanarea istorică și pot diferi de modelul actualizat. Consensul fără marjă este un reper descriptiv, nu adevărul probabilității.</p>' +
      '<div class="table-scroll"><table><thead><tr><th>Meci</th><th>Case</th><th>Abatere maximă</th><th>Model / consens 1X2</th></tr></thead><tbody>' + rows +
      '</tbody></table></div><p class="meta">Diferențele mari sunt motive de carantină. Independența economică a caselor nu este demonstrată. Reguli: 1X2 pre-match; compatibilitatea exactă de decontare cu operatorii RO rămâne neverificată.</p>';
  }
  function clearResult() { el('manual-result').textContent = 'Alege meciul, selecția și cota. Comparația nu verifică oferta și nu este un semnal de pariere.'; }
  function renderMatches() {
    const select = el('manual-match'), old = select.value;
    manualGames.clear();
    for (const fixture of VR.liveFixtures()) if (Number.isFinite(VR.kickoff(fixture))) manualGames.set(VR.fixtureId(fixture), fixture);
    select.innerHTML = '<option value="">Alege un meci…</option>' + Array.from(manualGames.entries()).map(([id, f]) =>
      '<option value="' + esc(id) + '">' + esc(VR.dateTime(new Date(VR.kickoff(f)).toISOString()) + ' · ' + f.home + ' — ' + f.away) + '</option>').join('');
    if (manualGames.has(old)) select.value = old;
    const enabled = manualGames.size > 0;
    for (const id of ['manual-match', 'manual-market', 'manual-outcome', 'manual-book', 'manual-price', 'manual-compare']) el(id).disabled = !enabled;
    if (!enabled) el('manual-result').textContent = 'Comparație blocată: lipsesc meciuri viitoare cu oră verificabilă și date proaspete.';
    else clearResult();
    updateLine();
  }
  function updateLine() {
    const f = manualGames.get(el('manual-match').value), market = el('manual-market').value;
    const p = f && f.markets[market === 'h2h' ? 'goals' : market];
    el('manual-line').textContent = market === 'h2h' ? 'Regulă obligatorie: rezultat la 90 de minute plus timpul adițional, fără reprize suplimentare.' :
      'Linia obligatorie a modelului: ' + (p && VR.isNumber(p.line) ? p.line : 'indisponibilă') + '. Verifică aceleași reguli de numărare și de decontare la operator.';
  }
  function updateOutcomes() {
    el('manual-outcome').innerHTML = el('manual-market').value === 'h2h' ? '<option value="home">1 — Gazde</option><option value="draw">X — Egal</option><option value="away">2 — Oaspeți</option>' : '<option value="over">Peste linie</option><option value="under">Sub linie</option>';
    updateLine(); clearResult();
  }
  for (const id of ['manual-match', 'manual-book', 'manual-outcome', 'manual-price']) el(id).addEventListener('change', () => { updateLine(); clearResult(); });
  el('manual-market').addEventListener('change', updateOutcomes);
  el('manual-compare').addEventListener('click', () => {
    const id = el('manual-match').value, fixture = manualGames.get(id), odd = Number(el('manual-price').value);
    if (!window.DATA || !VR.freshness(window.DATA.generated_at).fresh || !fixture || !VR.upcoming(fixture) || !Number.isFinite(VR.kickoff(fixture))) {
      el('manual-result').textContent = 'Comparație blocată: selectează explicit un meci viitor, cu date proaspete.'; return;
    }
    if (!Number.isFinite(odd) || odd < 1.02 || odd > 100) { el('manual-result').textContent = 'Introdu o cotă validă între 1,02 și 100.'; return; }
    const market = el('manual-market').value, outcome = el('manual-outcome').value, model = fixture.markets[market === 'h2h' ? 'goals' : market];
    if (!VR.marketAvailable(model)) {
      el('manual-result').textContent = 'Comparație blocată: ' + (model && model.availability && model.availability.message || 'Istoricul statistic este vechi sau nu poate fi verificat.'); return;
    }
    const valid = model && (market === 'h2h' ? VR.distribution(model.h2h) : VR.probability(model.over) && VR.probability(model.under) && Math.abs(model.over + model.under - 1) <= .0001 && VR.isNumber(model.line));
    if (!valid) { el('manual-result').textContent = 'Comparație blocată: statistici insuficiente sau probabilități invalide pentru această piață.'; return; }
    const p = market === 'h2h' ? model.h2h[outcome] : model[outcome];
    if (!VR.probability(p) || p <= 0 || p >= 1) { el('manual-result').textContent = 'Probabilitate invalidă; comparația a fost blocată.'; return; }
    const warnings = ['Oferta, timestamp-ul și regulile operatorului sunt neverificate', 'model fără calibrare prospectivă demonstrată'];
    if (model.small_sample || model.quality === 'very_low') warnings.push('eșantion statistic redus');
    if (Math.abs(p - 1 / odd) >= .10) warnings.push('diferență de cel puțin 10 puncte procentuale: carantină');
    el('manual-result').innerHTML = '<b>' + esc(el('manual-book').value) + ' · ' + esc(fixture.home) + ' — ' + esc(fixture.away) + '</b><div>Estimare model: ' + pct(p) +
      ' · Prag matematic 1/cotă: ' + pct(1 / odd) + '</div><div class="meta"><b>Nu este un semnal de pariere.</b> ' + esc(warnings.join('; ')) +
      '. Nu există un interval validat pentru eroarea probabilității acestui meci. Nu afișăm EV drept oportunitate de profit.</div>';
  });
  window.addEventListener('valueradar:datachanged', renderMatches);
  window.addEventListener('valueradar:refresh', reload);
  renderMatches(); reload();
  setInterval(reload, 15 * 60e3);
}());
