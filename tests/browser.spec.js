const { test, expect } = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');
const read = name => JSON.parse(fs.readFileSync(path.join(__dirname, '../docs', name), 'utf8'));
const clone = value => JSON.parse(JSON.stringify(value));
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
