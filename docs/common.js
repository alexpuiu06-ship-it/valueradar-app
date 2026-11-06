/* Shared display guards. A timestamp without an explicit zone is not evidence. */
(function () {
  'use strict';
  const VR = window.VR = {};
  VR.el = id => document.getElementById(id);
  VR.esc = value => String(value == null ? '' : value).replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;');
  VR.isNumber = value => typeof value === 'number' && Number.isFinite(value);
  VR.probability = value => VR.isNumber(value) && value >= 0 && value <= 1;
  VR.distribution = value => value && ['home', 'draw', 'away'].every(k => VR.probability(value[k])) &&
    Math.abs(value.home + value.draw + value.away - 1) <= 0.0001;
  VR.pct = value => VR.probability(value) ? '≈' + (100 * value).toFixed(1) + '%' : '—';
  VR.fmt = (value, places = 2) => VR.isNumber(value) ? value.toFixed(places) : '—';
  VR.timestamp = value => {
    if (typeof value !== 'string') return NaN;
    const parts = value.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?(Z|[+-]\d{2}:\d{2})$/);
    if (!parts) return NaN;
    const [, year, month, day, hour, minute, second] = parts;
    if (+month < 1 || +month > 12 || +day < 1 || +day > new Date(Date.UTC(+year, +month, 0)).getUTCDate() || +hour > 23 || +minute > 59 || +(second || 0) > 59) return NaN;
    return Date.parse(value);
  };
  VR.freshness = (value, maxHours = 12) => {
    const stamp = VR.timestamp(value), age = Date.now() - stamp;
    return { valid: Number.isFinite(stamp), fresh: Number.isFinite(stamp) && age >= -5 * 60e3 && age <= maxHours * 3600e3,
      future: Number.isFinite(stamp) && age < -5 * 60e3, stamp };
  };
  VR.dateTime = value => Number.isFinite(VR.timestamp(value)) ? new Intl.DateTimeFormat('ro-RO', {
    dateStyle: 'short', timeStyle: 'short', timeZone: 'Europe/Bucharest'
  }).format(new Date(value)) + ' (România)' : 'necunoscut';
  VR.fetchJSON = async path => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch(path + '?v=' + Date.now(), { cache: 'no-store', signal: controller.signal });
      if (!response.ok) throw Error('HTTP ' + response.status);
      return await response.json();
    } catch (error) {
      if (error.name === 'AbortError') throw Error('Timpul de așteptare a expirat (8 secunde).');
      throw error;
    } finally { clearTimeout(timer); }
  };
  VR.kickoff = fixture => {
    if (fixture.kickoff_utc != null) return VR.timestamp(fixture.kickoff_utc);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(fixture.date || '') || !/^\d{2}:\d{2}$/.test(fixture.time || '')) return NaN;
    return VR.timestamp(fixture.date + 'T' + fixture.time + ':00+01:00');
  };
  VR.upcoming = fixture => {
    const kickoff = VR.kickoff(fixture);
    return Number.isFinite(kickoff) ? kickoff > Date.now() : /^\d{4}-\d{2}-\d{2}$/.test(fixture.date || '') && fixture.date > new Date().toISOString().slice(0, 10);
  };
  VR.fixtureId = fixture => JSON.stringify([fixture.league, fixture.date, fixture.home, fixture.away]);
  VR.liveFixtures = () => window.DATA && VR.freshness(window.DATA.generated_at).fresh && Array.isArray(window.DATA.fixtures) ? window.DATA.fixtures.filter(VR.upcoming) : [];
  VR.x3 = distribution => VR.distribution(distribution) ? ['home', 'draw', 'away'].map((k, i) => ['1', 'X', '2'][i] + ': ' + VR.pct(distribution[k])).join(' · ') : 'Probabilități indisponibile sau invalide';
  VR.interval = value => Array.isArray(value) && value.length === 2 && value.every(VR.isNumber) ? '[' + value.map(x => VR.fmt(x, 4)).join(', ') + ']' : 'insuficient';
  VR.intervalVerdict = value => !Array.isArray(value) || value.length !== 2 || !value.every(VR.isNumber) ? 'Prea puține date pentru o concluzie.' :
    value[0] <= 0 && value[1] >= 0 ? 'Diferența este neconcludentă.' : value[1] < 0 ? 'Rezultatul preliminar favorizează modelul de referință.' : 'Rezultatul preliminar favorizează candidatul; necesită confirmare prospectivă.';
}());
