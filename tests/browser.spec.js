const { test, expect } = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');
const read = name => JSON.parse(fs.readFileSync(path.join(__dirname, '../docs', name), 'utf8'));
const clone = value => JSON.parse(JSON.stringify(value));
const recorded = name => JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', name), 'utf8'));
const original = read('latest.json');
const fixedNow = Date.parse(original.generated_at) + 60000;
const kickoff = f => Date.parse(f.kickoff_utc || `${f.date}T${f.time}:00+01:00`);
const upcomingFixture = original.fixtures.find(f => kickoff(f) > fixedNow && f.markets.goals && f.markets.goals.h2h);
if (!upcomingFixture) throw Error('Browser tests require a real forecast with known future kickoff in docs/latest.json');
const id = f => JSON.stringify([f.league, f.date, f.home, f.away]);
async function serveLatest(page, data = original) {
  await page.route('**/latest.json?*', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify(data) }));
}
async function open(page, data = original) {
  await page.clock.install({ time: fixedNow });
  await serveLatest(page, data);
  await page.goto('/');
}
async function ready(page) {
  await expect(page.locator('#fixtures .card').first()).toBeVisible();
  await expect(page.locator('#manual-compare')).toBeEnabled();
}

function operationsFor(data = original) {
  // Recorded aggregate shape; align its timestamps to the deterministic UI clock.
  const report = clone(recorded('operations_report.json'));
  report.generated_at = new Date(fixedNow).toISOString();
  report.analysis_generated_at = data.generated_at;
  report.pipeline_version = data.pipeline_version;
  report.settlement.generated_at = data.generated_at;
  report.ro_history.last_observed_at = new Date(fixedNow - 60000).toISOString();
  return report;
}
function historyAt(times) {
  const report = clone(recorded('ro_feed_history.json'));
  const base = report.records[0];
  report.generated_at = new Date(fixedNow).toISOString();
  report.records = times.map(stamp => {
    const row = clone(base);
    row.observed_at = new Date(stamp).toISOString();
    const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Bucharest', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date(stamp));
    row.day_ro = ['year', 'month', 'day'].map(k => parts.find(p => p.type === k).value).join('-');
    for (const league of row.leagues) league.received_at = new Date(stamp - 1000).toISOString();
    return row;
  });
  return report;
}

test('real forecasts: filters, arithmetic explanations and honest research panels', async ({ page }) => {
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await open(page); await ready(page);
  await page.getByLabel('Campionat', { exact: true }).selectOption(upcomingFixture.league);
  await expect(page.locator('#fixtures .card').first()).toContainText(upcomingFixture.league);
  await page.getByLabel('Piață analizată', { exact: true }).selectOption('goals');
  const first = page.locator('#fixtures .card').first();
  await first.locator('summary').click();
  await expect(first).toContainText('media regularizată');
  await expect(first).toContainText('Lambda gazde');
  await expect(first).toContainText('Incertitudine');
  await expect(first).toContainText('Surse folosite');
  await expect(page.locator('#model-lab-report')).toContainText('Log-loss actual');
  await expect(page.locator('#elo-summary')).toContainText('N test final:');
  await expect(page.locator('#odds-list')).toContainText('Nu există pariuri value verificate');
  expect(errors).toEqual([]);
});

test('manual comparison requires an explicit match and supports h2h and exact total line', async ({ page }) => {
  await open(page); await ready(page);
  await page.getByLabel('Cota', { exact: true }).fill('2.10');
  await page.locator('#manual-compare').click();
  await expect(page.locator('#manual-result')).toContainText('selectează explicit');
  await page.getByLabel('Meci', { exact: true }).selectOption(id(upcomingFixture));
  await page.locator('#manual-compare').click();
  await expect(page.locator('#manual-result')).toContainText('Nu este un semnal de pariere');
  await expect(page.locator('#manual-result')).toContainText('1/cotă');
  await page.getByLabel('Piața', { exact: true }).selectOption('goals');
  await expect(page.locator('#manual-line')).toContainText('2.5');
  await page.getByLabel('Selecția', { exact: true }).selectOption('under');
  await page.locator('#manual-compare').click();
  await expect(page.locator('#manual-result')).toContainText('Estimare model');
  await expect(page.locator('#manual-result')).not.toContainText('profit garantat');
});

test('real calibration report renders aligned models, league scores and uncertainty', async ({ page }) => {
  const report = read('calibration_report.json');
  // Use the real report timestamp without depending on when CI happens to run.
  await page.route('**/calibration_report.json?*', route => route.fulfill({ json: report }));
  await open(page); await ready(page);
  const panel = page.locator('#calibration-report');
  await expect(panel).toContainText('Poisson calibrat');
  await expect(panel).toContainText('Ensemble calibrat');
  await expect(panel).toContainText('studiu exploratoriu');
  await expect(panel).toContainText('bootstrap pe săptămâni ISO');
  await expect(panel).toContainText('indisponibil');
  const league = Object.keys(report.holdout.by_league)[0];
  await panel.locator('summary').filter({ hasText: league }).click();
  await expect(panel).toContainText(league);
  await expect(panel).toContainText('Calibrarea pe grupe');
});

test('prospective score uses the current pipeline version and never borrows legacy results', async ({ page }) => {
  const data = clone(original);
  data.pipeline_version = 'test_current_pipeline';
  data.prospective.h2h = { n: 50, brier: .12345, by_pipeline_version: {
    test_current_pipeline: { n: 2, brier: .25 }, legacy_unversioned: { n: 48, brier: .10 }
  } };
  await page.clock.install({ time: fixedNow });
  await page.route('**/latest.json?*', route => route.fulfill({ json: data }));
  await page.goto('/'); await ready(page);
  const score = page.locator('#prospective-current');
  await expect(score).toContainText('test_current_pipeline: predicții prospective decontate 2; Brier 0.25000');
  await expect(score).toContainText('Alte versiuni în jurnal: 48');
  await expect(score).toContainText('nu validează modelul corectat');
  await expect(score).not.toContainText('0.12345');
  delete data.prospective.h2h.by_pipeline_version.test_current_pipeline;
  await page.locator('#refresh').click();
  await expect(score).toContainText('predicții prospective decontate 0; Brier —');
  await expect(score).toContainText('Alte versiuni în jurnal: 50');
});

test('manual selector contains every usable fixture, including beyond the former 100 limit', async ({ page }) => {
  await open(page); await ready(page);
  const valid = original.fixtures.filter(f => kickoff(f) > fixedNow);
  await expect(page.locator('#manual-match option')).toHaveCount(valid.length + 1);
  const last = valid.at(-1);
  await page.getByLabel('Meci', { exact: true }).selectOption(id(last));
  await page.getByLabel('Cota', { exact: true }).fill('2');
  await page.locator('#manual-compare').click();
  const result = page.locator('#manual-result');
  if (last.markets.goals && last.markets.goals.h2h) await expect(result).toContainText(last.home);
  else await expect(result).toContainText('statistici insuficiente');
});

for (const [label, timestamp, expected] of [
  ['stale', new Date(fixedNow - 13 * 3600e3).toISOString(), 'peste 12 ore'],
  ['future', new Date(fixedNow + 3600e3).toISOString(), 'în viitor'],
  ['invalid', 'not-a-date', 'timestamp valid'],
  ['no timezone', new Date(fixedNow).toISOString().replace('Z', ''), 'timestamp valid'],
  ['missing', null, 'timestamp valid']
]) {
  test(`${label} timestamp hides probabilities and disables manual comparison`, async ({ page }) => {
    const data = clone(original); data.generated_at = timestamp;
    await open(page, data);
    await expect(page.locator('#message')).toContainText(expected);
    await expect(page.locator('#fixtures .pill')).toHaveCount(0);
    await expect(page.locator('#manual-compare')).toBeDisabled();
    await expect(page.locator('#odds-list')).toContainText('Nu există pariuri value verificate');
  });
}

test('offline initial response fails closed', async ({ page }) => {
  await page.clock.install({ time: fixedNow });
  await page.route('**/latest.json?*', route => route.abort('internetdisconnected'));
  await page.goto('/');
  await expect(page.locator('#message')).toContainText('Comparațiile sunt blocate');
  await expect(page.locator('#manual-compare')).toBeDisabled();
  await expect(page.locator('#fixtures .pill')).toHaveCount(0);
});

test('failed refresh clears previously shown probabilities and manual results', async ({ page }) => {
  await page.clock.install({ time: fixedNow });
  let requests = 0;
  await page.route('**/latest.json?*', route => ++requests === 1 ? route.fulfill({ contentType: 'application/json', body: JSON.stringify(original) }) : route.abort('internetdisconnected'));
  await page.goto('/'); await ready(page);
  await page.getByLabel('Meci', { exact: true }).selectOption(id(upcomingFixture));
  await page.getByLabel('Cota', { exact: true }).fill('2');
  await page.locator('#manual-compare').click();
  await expect(page.locator('#manual-result')).toContainText(upcomingFixture.home);
  await page.locator('#refresh').click();
  await expect(page.locator('#message')).toContainText('Comparațiile sunt blocate');
  await expect(page.locator('#manual-compare')).toBeDisabled();
  await expect(page.locator('#manual-result')).not.toContainText(upcomingFixture.home);
  await expect(page.locator('#fixtures .pill')).toHaveCount(0);
});

test('slow forecast response beyond three seconds still synchronizes all selectors', async ({ page }) => {
  await page.clock.install({ time: fixedNow });
  await page.route('**/latest.json?*', async route => {
    await new Promise(resolve => setTimeout(resolve, 3500));
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(original) });
  });
  await page.goto('/');
  await expect(page.locator('#manual-compare')).toBeDisabled();
  await ready(page);
  await expect(page.locator('#manual-match option')).not.toHaveCount(1);
});

test('network timeout is bounded and leaves no stale data', async ({ page }) => {
  await page.clock.install({ time: fixedNow });
  await page.route('**/latest.json?*', () => {});
  await page.goto('/');
  await page.clock.runFor(8100);
  await expect(page.locator('#message')).toContainText('8 secunde');
  await expect(page.locator('#manual-compare')).toBeDisabled();
  await expect(page.locator('#fixtures .pill')).toHaveCount(0);
});

test('forged watchlist and ROI flags cannot create verified value content', async ({ page }) => {
  await page.route('**/odds_watchlist.json?*', route => route.fulfill({ json: { status: 'verified_ro_opportunities', live_ro_supported: true, items: [{ ...upcomingFixture, bookmaker: 'PROFIT GARANTAT', verified_value: true, ready_to_bet: true, odds: 100, estimated_ev: 100 }] } }));
  await page.route('**/market_audit.json?*', route => route.fulfill({ json: { observations: 12, initial_positive_ev_signals: 100, hypothetical_roi: 25, model_is_verified: true, quotes_are_verified_romania: true } }));
  await open(page); await ready(page);
  await expect(page.locator('#odds-list')).toContainText('Nu există pariuri value verificate');
  await expect(page.locator('#market-review')).toContainText('ROI nu sunt validate');
  await expect(page.locator('body')).not.toContainText('PROFIT GARANTAT');
});

test('quote attempt timestamp cannot make old or missing source quotes fresh', async ({ page }) => {
  await page.route('**/odds_status.json?*', route => route.fulfill({ json: { status: 'connected', checked_at: new Date(fixedNow).toISOString(), data_timestamp: 'invalid' } }));
  await open(page); await ready(page);
  await expect(page.locator('#odds-status')).toContainText('timestamp invalid');
  await expect(page.locator('#odds-list')).toContainText('Nu există pariuri value verificate');
});

test('invalid probabilities are hidden and manual comparison is blocked', async ({ page }) => {
  const data = clone(original), fixture = clone(upcomingFixture);
  fixture.markets.goals.h2h = { home: .9, draw: .9, away: -.8 };
  data.fixtures = [fixture];
  await open(page, data); await ready(page);
  await expect(page.locator('#fixtures')).toContainText('Probabilități invalide');
  await expect(page.locator('#fixtures .pill')).toHaveCount(0);
  await page.getByLabel('Meci', { exact: true }).selectOption(id(fixture));
  await page.getByLabel('Cota', { exact: true }).fill('2');
  await page.locator('#manual-compare').click();
  await expect(page.locator('#manual-result')).toContainText('probabilități invalide');
});

test('already started fixtures are removed from cards and manual selector', async ({ page }) => {
  const data = clone(original), fixture = clone(upcomingFixture);
  fixture.kickoff_utc = new Date(fixedNow - 60000).toISOString();
  data.fixtures = [fixture];
  await open(page, data);
  await expect(page.locator('#fixtures')).toContainText('Nu sunt meciuri viitoare');
  await expect(page.locator('#manual-compare')).toBeDisabled();
});

test('Romania kickoff date rolls over at midnight and external text is escaped', async ({ page }) => {
  const data = clone(original), fixture = clone(upcomingFixture);
  fixture.date = new Date(fixedNow + 86400e3).toISOString().slice(0, 10);
  fixture.time = '23:30'; delete fixture.kickoff_utc;
  fixture.home = '<img src=x onerror="window.uiInjected=true">';
  data.fixtures = [fixture];
  await open(page, data); await ready(page);
  const expected = new Intl.DateTimeFormat('ro-RO', { dateStyle: 'short', timeStyle: 'short', timeZone: 'Europe/Bucharest' }).format(new Date(kickoff(fixture)));
  await expect(page.locator('#fixtures .league')).toContainText(expected);
  await expect(page.locator('#fixtures h2')).toContainText('<img');
  await expect(page.locator('#fixtures img')).toHaveCount(0);
  expect(await page.evaluate(() => window.uiInjected)).toBeUndefined();
});

test('mobile and desktop layout has no document-level horizontal overflow', async ({ page }) => {
  await open(page); await ready(page);
  const widths = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
  expect(widths.scroll).toBeLessThanOrEqual(widths.client + 1);
});


test('minute timer preserves open explanations and completed manual comparison', async ({ page }) => {
  await open(page); await ready(page);
  const details = page.locator('#fixtures .explanation').first();
  await details.locator('summary').click();
  await page.locator('#manual-match').selectOption(id(upcomingFixture));
  await page.locator('#manual-price').fill('2.10');
  await page.locator('#manual-compare').click();
  const result = await page.locator('#manual-result').textContent();
  await page.clock.fastForward(61000);
  await expect(details).toHaveAttribute('open', '');
  await expect(page.locator('#manual-result')).toHaveText(result);
});

test('fresh execution with old underlying history blocks cards and manual comparison', async ({ page }) => {
  const data = clone(original);
  for (const f of data.fixtures) for (const p of Object.values(f.markets)) if (p) {
    p.explanation.last_observation_date = '2026-05-24';
    p.availability = { comparison_allowed: false, message: 'Istoric vechi; comparație blocată.' };
  }
  data.source_report = [{ league: upcomingFixture.league, kind: 'results', ok: false }];
  data.source_success = data.source_total - 1;
  await open(page, data); await ready(page);
  await expect(page.locator('#fixtures .pill')).toHaveCount(0);
  await expect(page.locator('#fixtures .card').first()).toContainText('Istoric vechi');
  await page.locator('#data-health summary').click();
  await expect(page.locator('#data-health')).toContainText('rezultate curente');
  await page.locator('#manual-match').selectOption(id(upcomingFixture));
  await page.locator('#manual-price').fill('2.10');
  await page.locator('#manual-compare').click();
  await expect(page.locator('#manual-result')).toContainText('blocată');
  await expect(page.locator('#manual-result')).not.toContainText('Estimare model');
});

test('Elo from a different data pipeline cannot be paired with current forecasts', async ({ page }) => {
  const report = clone(read('elo_challenger.json'));
  report.protocol.model_pipeline_version = 'different_pipeline_test_only';
  await page.route('**/elo_challenger.json?*', route => route.fulfill({ json: report }));
  await open(page); await ready(page);
  await expect(page.locator('#elo-summary')).toContainText('different_pipeline_test_only');
  await expect(page.locator('#elo-match')).toBeDisabled();
  await expect(page.locator('#elo-compare')).toContainText('aceeași versiune');
});

test('RO panel displays real aggregate coverage as a historical unverified snapshot', async ({ page }) => {
  const report = clone(read('ro_feed_status.json'));
  report.generated_at = new Date(fixedNow - 60000).toISOString();
  await page.route('**/ro_feed_status.json?*', route => route.fulfill({ json: report }));
  await open(page); await ready(page);
  await expect(page.locator('#ro-feed-status')).toContainText('Fotografie istorică');
  await expect(page.locator('#ro-feed-status')).toContainText('120 secunde');
  const rows = page.locator('#ro-feed-coverage tbody tr');
  await expect(rows).toHaveCount(5);
  for (let i = 0; i < report.leagues.length; i++) {
    const row = report.leagues[i];
    await expect(rows.nth(i)).toContainText(row.league);
    for (const [index, book] of ['superbet_ro', 'netbet_ro'].entries()) {
      const d = row.quality && row.quality.book_diagnostics[book];
      await expect(rows.nth(i).locator('td').nth(index + 1)).toContainText(d ? `${d.complete_recent_markets} / ${d.matched_current_model_markets}` : '—');
    }
  }
  await expect(page.locator('#ro-feed-module')).toContainText('nu oferte actuale confirmate');
  await expect(page.locator('#ro-feed-module')).toContainText('Nu există pariuri value verificate');
});

test('expired RO snapshot is explicit and missing diagnostics do not block the app', async ({ page }) => {
  const report = clone(read('ro_feed_status.json'));
  report.generated_at = new Date(fixedNow - 25 * 3600000).toISOString();
  await page.route('**/ro_feed_status.json?*', route => route.fulfill({ json: report }));
  await open(page); await ready(page);
  await expect(page.locator('#ro-feed-status')).toContainText('peste 24 de ore');
  await page.route('**/ro_feed_status.json?*', route => route.abort('failed'));
  await page.locator('#refresh').click();
  await ready(page);
  await expect(page.locator('#ro-feed-status')).toContainText('indisponibil');
  await expect(page.locator('#ro-feed-coverage tbody tr')).toHaveCount(0);
});

test('RO coverage never trusts verified flags or inserts diagnostic HTML', async ({ page }) => {
  const report = clone(read('ro_feed_status.json'));
  report.generated_at = new Date(fixedNow - 60000).toISOString();
  const q = report.leagues.find(row => row.quality).quality;
  q.rejection_counts['<img src=x onerror="window.roInjected=true">'] = 1;
  await page.route('**/ro_feed_status.json?*', route => route.fulfill({ json: report }));
  await open(page); await ready(page);
  await expect(page.locator('#ro-feed-coverage')).toContainText('<img');
  await expect(page.locator('#ro-feed-coverage img')).toHaveCount(0);
  expect(await page.evaluate(() => window.roInjected)).toBeUndefined();
  report.verified_value = true;
  await page.locator('#refresh').click();
  await expect(page.locator('#ro-feed-status')).toContainText('invalid');
  await expect(page.locator('#ro-feed-coverage tbody tr')).toHaveCount(0);
  await expect(page.locator('#odds-list')).toContainText('Nu există pariuri value verificate');
});

test('settlement panel uses recorded counts and separates the current pipeline', async ({ page }) => {
  const report = operationsFor();
  await page.route('**/operations_report.json?*', route => route.fulfill({ json: report }));
  await open(page); await ready(page);
  const counts = report.settlement.by_pipeline_version[original.pipeline_version];
  await expect(page.locator('#settlement-current')).toContainText(String(Object.values(counts).reduce((a, b) => a + b, 0)));
  await expect(page.locator('#settlement-summary')).toContainText('meciuri distincte');
  await page.locator('#settlement-details summary').click();
  await expect(page.locator('#settlement-details')).toContainText('Așteaptă rezultat disponibil');
  await expect(page.locator('#operations-monitor')).toContainText('Nu confirmă regulile unui operator');
  await expect(page.locator('#odds-list')).toContainText('Nu există pariuri value verificate');
});

test('supplementary scores explain evaluation scope and cannot claim training or profit validation', async ({ page }) => {
  const data = clone(original), report = operationsFor(data);
  const counts = report.settlement.by_pipeline_version[data.pipeline_version];
  counts.upcoming -= 8; counts.settled_with_evidence = 8;
  data.pipeline_execution = { ...(data.pipeline_execution || {}), supplementary_scores: {
    eligible_matches: 4, eligible_forecasts: 8, training_use: false, value_enabled: false
  } };
  await page.route('**/operations_report.json?*', route => route.fulfill({ json: report }));
  await open(page, data); await ready(page);
  await expect(page.locator('#supplementary-scores')).toContainText('4 meciuri, 8 estimări');
  await expect(page.locator('#supplementary-scores')).toContainText('numai pentru evaluarea');
  await expect(page.locator('#supplementary-scores')).toContainText('nu confirmă calibrarea sau profitul');
  await expect(page.locator('#odds-list')).toContainText('Nu există pariuri value verificate');
  data.pipeline_execution.supplementary_scores.training_use = true;
  await page.locator('#refresh').click(); await ready(page);
  await expect(page.locator('#supplementary-scores')).toHaveCount(0);
});

test('monitoring warns about delayed analyses and probes while keeping the forecast window separate', async ({ page }) => {
  const data = clone(original);
  data.generated_at = new Date(fixedNow - 7 * 3600e3).toISOString();
  const report = operationsFor(data);
  report.ro_history.last_observed_at = new Date(fixedNow - 31 * 3600e3).toISOString();
  await page.route('**/operations_report.json?*', route => route.fulfill({ json: report }));
  await open(page, data); await ready(page);
  await expect(page.locator('#operations-alerts')).toContainText('peste 6 ore');
  await expect(page.locator('#operations-alerts')).toContainText('peste 30 de ore');
  await expect(page.locator('#fixtures .card').first()).toBeVisible();
});

test('minute monitor updates deadlines without closing settlement details', async ({ page }) => {
  const data = clone(original);
  data.generated_at = new Date(fixedNow - 6 * 3600e3 + 30000).toISOString();
  await page.route('**/operations_report.json?*', route => route.fulfill({ json: operationsFor(data) }));
  await open(page, data); await ready(page);
  await page.locator('#settlement-details summary').click();
  await expect(page.locator('#operations-alerts')).not.toContainText('peste 6 ore');
  await page.clock.fastForward(61000);
  await expect(page.locator('#operations-alerts')).toContainText('peste 6 ore');
  await expect(page.locator('#settlement-details')).toHaveAttribute('open', '');
});

test('missing and mismatched settlement reports cannot borrow counts or block the manual tool', async ({ page }) => {
  const report = operationsFor(); report.pipeline_version = 'different_test_pipeline';
  await page.route('**/operations_report.json?*', route => route.fulfill({ json: report }));
  await open(page); await ready(page);
  await expect(page.locator('#settlement-summary')).toContainText('nu este asociat');
  await expect(page.locator('#settlement-current')).toHaveCount(0);
  await page.route('**/operations_report.json?*', route => route.abort('failed'));
  await page.locator('#refresh').click(); await ready(page);
  await expect(page.locator('#operations-alerts')).toContainText('indisponibil');
  await expect(page.locator('#manual-compare')).toBeEnabled();
});

test('settlement diagnostics escape samples and reject profit or operator-verification flags', async ({ page }) => {
  const report = operationsFor();
  const sample = report.settlement.samples.find(row => row.pipeline_version === original.pipeline_version);
  sample.home = '<img src=x onerror="window.settlementInjected=true">';
  await page.route('**/operations_report.json?*', route => route.fulfill({ json: report }));
  await open(page); await ready(page);
  await page.locator('#settlement-details summary').click();
  await expect(page.locator('#settlement-details')).toContainText('<img');
  await expect(page.locator('#settlement-summary img')).toHaveCount(0);
  expect(await page.evaluate(() => window.settlementInjected)).toBeUndefined();
  report.settlement.operator_settlement_verified = true;
  await page.locator('#refresh').click();
  await expect(page.locator('#operations-alerts')).toContainText('invalid');
  await expect(page.locator('#settlement-current')).toHaveCount(0);
  report.settlement.operator_settlement_verified = false; report.hypothetical_roi = .5;
  await page.locator('#refresh').click();
  await expect(page.locator('#settlement-current')).toHaveCount(0);
});

test('RO history keeps missing days absent, preserves errors and retains the selected date on refresh', async ({ page }) => {
  const report = historyAt([fixedNow - 3 * 86400e3, fixedNow - 3600e3, fixedNow - 60000]);
  for (const row of report.records.at(-1).leagues) for (const d of Object.values(row.books)) {
    d.received = d.complete = d.matched = null;
  }
  await page.route('**/ro_feed_history.json?*', route => route.fulfill({ json: report }));
  await open(page); await ready(page);
  await page.locator('#ro-history-details summary').click();
  await expect(page.locator('#ro-history-status')).toContainText('3 probe observate în 2 zile');
  await expect(page.locator('#ro-history-day option')).toHaveCount(2);
  await expect(page.locator('#ro-history-table')).toContainText('probe fără răspuns evaluabil');
  await page.locator('#ro-history-day').selectOption(report.records[0].day_ro);
  await page.locator('#refresh').click();
  await expect(page.locator('#ro-history-day')).toHaveValue(report.records[0].day_ro);
  await expect(page.locator('#ro-history-table tbody tr')).toHaveCount(5);
});

test('invalid, duplicated and unavailable coverage history never creates positive coverage evidence', async ({ page }) => {
  const report = historyAt([fixedNow - 60000]); report.verified_value = true;
  await page.route('**/ro_feed_history.json?*', route => route.fulfill({ json: report }));
  await open(page); await ready(page);
  await page.locator('#ro-history-details summary').click();
  await expect(page.locator('#ro-history-status')).toContainText('invalid');
  await expect(page.locator('#ro-history-table tbody tr')).toHaveCount(0);
  report.verified_value = false; report.records.push(clone(report.records[0]));
  await page.locator('#refresh').click();
  await expect(page.locator('#ro-history-table tbody tr')).toHaveCount(0);
  await page.route('**/ro_feed_history.json?*', route => route.abort('failed'));
  await page.locator('#refresh').click(); await ready(page);
  await expect(page.locator('#ro-history-status')).toContainText('indisponibil');
  await expect(page.locator('#manual-compare')).toBeEnabled();
});
