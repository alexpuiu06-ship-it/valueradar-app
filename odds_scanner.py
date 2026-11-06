#!/usr/bin/env python3
"""ValueRadar: real pre-match odds adapter for The Odds API v4.

NO mock data in production, NO automatic betting, NO unfounded ROI claims.
Key comes ONLY from ODDS_API_KEY environment / GitHub Actions secret.
"""
from __future__ import annotations
import json, math, os, re, sys, statistics, urllib.request, urllib.error
from collections import Counter, defaultdict
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode

import runner

OUT=Path(__file__).resolve().parent/"docs"
SPORTS={"Premier League":"soccer_epl","La Liga":"soccer_spain_la_liga",
        "Serie A":"soccer_italy_serie_a","Bundesliga":"soccer_germany_bundesliga",
        "Ligue 1":"soccer_france_ligue_one"}
TARGET_BOOKS=["Superbet RO","Betano RO","Unibet RO","MrBit RO","NetBet RO","Casa Pariurilor"]
# The selected API currently covers UK/international books, not confirmed RO books.
REGION=os.getenv("ODDS_REGION","uk")
if REGION not in ("uk","eu","fr"):REGION="uk"
MAX_MONTHLY=400
MAX_PER_SCAN=5
MIN_RESERVE=70
FRESH_MAX_MINUTES=120
ALIASES={
 "manchesterunited":"manchesterunited","manutd":"manchesterunited",
 "manchestercity":"manchestercity","mancity":"manchestercity",
 "tottenhamhotspur":"tottenhamhotspur","tottenham":"tottenhamhotspur",
 "nottmforest":"nottinghamforest","nottinghamforest":"nottinghamforest",
 "brightonandhovealbion":"brighton","brighton":"brighton",
 "wolverhamptonwanderers":"wolves","wolves":"wolves",
 "newcastleunited":"newcastle","newcastle":"newcastle",
 "westhamunited":"westham","westham":"westham",
 "leedsunited":"leeds","leeds":"leeds","leicester city":"leicester",
 "parissaintgermain":"psg","parissg":"psg","psg":"psg",
 "internazionale":"inter","intermilan":"inter","inter":"inter",
 "borussiamonchengladbach":"monchengladbach",
 "bayernmunchen":"bayernmunich","bayernmunich":"bayernmunich",
 "athleticclub":"athleticbilbao","athleticbilbao":"athleticbilbao",
 "deportivoalaves":"alaves","alaves":"alaves",
 "atleticodemadrid":"atleticomadrid","atleticomadrid":"atleticomadrid",
 "brightonhovealbion":"brighton","wolverhampton":"wolves",
 "asmonaco":"monaco","monacofc":"monaco","olympiquedemarseille":"marseille",
 "olympiquemarseille":"marseille","stadebrestois":"brest",
 "stetienne":"saintetienne","saintetienne":"saintetienne",
 # Observed provider spellings verified against the model fixture identity
 # and exact kickoff; these aliases affect odds matching only.
 "coventrycity":"coventry","hullcity":"hull","betis":"realbetis",
 "paderborn07":"paderborn",
 "nottingham":"nottinghamforest","bilbao":"athleticbilbao","racingsantander":"racingdesantander",
 "realbetisbalompie":"realbetis","realbetis":"realbetis",
 "athletic":"athleticbilbao","borussiamgladbach":"monchengladbach"
}
def canonical(name):
 text=runner.norm(name)
 return ALIASES.get(text,text)
OUTCOMES = ("home", "draw", "away")
# No RO feed or prospective model validation is implemented. Observation flags
# are untrusted data and can never enable recommendations or simulated profit.
VALUE_BLOCKERS = (
 "romanian_operator_feed_not_verified",
 "market_line_and_settlement_not_verified",
 "model_calibration_not_prospectively_validated",
 "positive_edge_after_uncertainty_not_demonstrated",
)

def value_blockers(offer=None):
 return list(VALUE_BLOCKERS)

def dt(value):
 """Only an explicit UTC offset establishes an instant; never invent one."""
 try:
  d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
  return d.astimezone(timezone.utc) if d.tzinfo and d.utcoffset() is not None else None
 except (ValueError, TypeError, OverflowError):
  return None

def finite_number(value, low, high):
 return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and low <= value <= high

def valid_probabilities(probs):
 return (isinstance(probs, dict) and set(probs) == set(OUTCOMES)
  and all(finite_number(probs[k], 0, 1) for k in OUTCOMES)
  and abs(sum(probs.values()) - 1) <= 0.00005)

def get_json(url):
 # URL includes key. Avoid logging URLs, request objects, or exception details.
 try:
  request = urllib.request.Request(url, headers={"User-Agent": "ValueRadar-educational-odds/0.2"})
  with urllib.request.urlopen(request, timeout=16) as res:
   return json.loads(res.read(3000000).decode("utf8")), dict(res.headers.items()), None
 except urllib.error.HTTPError as exc:
  return [], {}, f"API HTTP {exc.code} (verifică abonamentul, cheia și creditul)"
 except Exception as exc:
  return [], {}, f"Network/API error: {type(exc).__name__}"

def read_json(name, default):
 try:
  return json.loads((OUT/name).read_text(encoding="utf-8"))
 except (OSError, ValueError, TypeError):
  return default

def write_json(name, data):
 OUT.mkdir(parents=True, exist_ok=True)
 path = OUT/name
 temporary = path.with_suffix(path.suffix + ".tmp")
 temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
 temporary.replace(path)

def status(mode, **details):
 now = datetime.now(timezone.utc).isoformat()
 s = {"status": mode, "checked_at": now, "attempted_at": now,
  "data_timestamp": None, "last_successful_quote_at": None,
  "provider": "The Odds API v4", "region": REGION, "market": "h2h",
  "bookmakers_ro_confirmed": False, "bookmakers_ro_requested": TARGET_BOOKS,
  "value_blockers": value_blockers(), "watchlist_count": 0,
  "budget_accounting": "conservative_request_reservations",
  "note": "Only international observations; no verified Romanian bookmaker feed.", **details}
 write_json("odds_status.json", s)
 return s

def close_watchlist(mode="no_verified_opportunities"):
 write_json("odds_watchlist.json", {
  "generated_at": datetime.now(timezone.utc).isoformat(),
  "provider": "The Odds API v4", "region": REGION,
  "live_ro_supported": False, "status": "no_verified_opportunities",
  "scan_state": mode, "value_blockers": value_blockers(),
  "recommendation": "Nu există pariuri value verificate.", "items": []})

def match_event(e, fixtures, now):
 """Exact explicit aliases, correct competition and same kickoff instant only."""
 if not isinstance(e, dict):
  return None
 home, away = canonical(e.get("home_team", "")), canonical(e.get("away_team", ""))
 start = dt(e.get("commence_time"))
 if not home or not away or home == away or not start or not now < start <= now+timedelta(days=30):
  return None
 matches = []
 for f in fixtures:
  if not isinstance(f, dict) or f.get("league") not in SPORTS:
   continue
  if e.get("sport_key") and e["sport_key"] != SPORTS[f["league"]]:
   continue
  kickoff = runner.fixture_kickoff(f)
  if not kickoff or not kickoff > now or abs((start-kickoff).total_seconds()) > 60:
   continue
  if home == canonical(f.get("home", "")) and away == canonical(f.get("away", "")):
   matches.append(f)
 # A duplicate or ambiguous fixture is a data issue, never a guessed match.
 return matches[0] if len(matches) == 1 else None

def quote_source_timestamp(bookmaker):
 markets = bookmaker.get("markets", []) if isinstance(bookmaker, dict) else []
 if not isinstance(markets, list):
  return None
 h2h = [m for m in markets if isinstance(m, dict) and m.get("key") == "h2h"]
 if len(h2h) != 1:
  return None
 value = h2h[0].get("last_update")
 return dt(value if value is not None else bookmaker.get("last_update"))

def parse_h2h(bookmaker, event, now):
 if not isinstance(bookmaker, dict) or not isinstance(event, dict):
  return None
 source_update = quote_source_timestamp(bookmaker)
 if source_update is None or not 0 <= (now-source_update).total_seconds()/60 <= FRESH_MAX_MINUTES:
  return None
 markets = [m for m in bookmaker.get("markets", []) if isinstance(m, dict) and m.get("key") == "h2h"]
 market = markets[0]
 if market.get("point") is not None:
  return None
 outcomes = market.get("outcomes", [])
 if not isinstance(outcomes, list) or len(outcomes) != 3:
  return None
 event_home, event_away = canonical(event.get("home_team", "")), canonical(event.get("away_team", ""))
 if not event_home or not event_away or event_home == event_away:
  return None
 prices = {}
 for item in outcomes:
  if not isinstance(item, dict) or item.get("point") is not None:
   return None
  name, price = item.get("name", ""), item.get("price")
  if not finite_number(price, 1.01, 1000):
   return None
  outcome = "draw" if str(name).casefold() in ("draw", "tie", "x") else (
   "home" if canonical(name) == event_home else "away" if canonical(name) == event_away else None)
  if outcome is None or outcome in prices:
   return None
  prices[outcome] = float(price)
 if set(prices) != set(OUTCOMES):
  return None
 overround = sum(1/x for x in prices.values())
 if not .85 <= overround <= 1.5:
  return None
 return prices, round(overround-1, 5), round((now-source_update).total_seconds()/60, 1)

def analyze_fixture(e, f, now, model_generated_at=None, model_pipeline_version=None):
 markets = f.get("markets", {}) if isinstance(f, dict) else {}
 model = (markets.get("goals") or {}) if isinstance(markets, dict) else {}
 probs = model.get("h2h") if isinstance(model, dict) else None
 if not valid_probabilities(probs) or not runner.comparison_allowed(model,now):
  return [], 0, 0
 sample_sizes = [model.get("n_home"), model.get("n_away")]
 sample_ok = not bool(model.get("small_sample")) and all(finite_number(value, 8, 1000000) for value in sample_sizes)
 parsed, seen_books, offers = 0, set(), []
 books = e.get("bookmakers", []) if isinstance(e, dict) else []
 if not isinstance(books, list):
  return [], 0, 0
 # Repeated bookmaker IDs are ambiguous; never count them as independent.
 counts = Counter(str(b.get("key", "")) for b in books if isinstance(b, dict))
 for book in books:
  if not isinstance(book, dict):
   continue
  book_id = str(book.get("key", ""))
  if not book_id or counts[book_id] != 1:
   continue
  quote = parse_h2h(book, e, now)
  if not quote:
   continue
  prices, margin, age = quote
  parsed += 1
  seen_books.add(book_id)
  den = sum(1/v for v in prices.values())
  for outcome, odd in prices.items():
   p = float(probs[outcome])
   offers.append({"league": f["league"], "date": f["date"], "home": f["home"], "away": f["away"],
    "bookmaker": str(book.get("title", "Unknown")), "bookmaker_id": book_id,
    "outcome": outcome, "odds": odd, "model_probability": p,
    "market_probability_no_vig": round((1/odd)/den, 5), "estimated_ev": round(p*odd-1, 5),
    "price_margin": margin, "quote_age_minutes": age, "model_low_sample": not sample_ok,
    "observed_at": now.isoformat(), "quote_timestamp": quote_source_timestamp(book).isoformat(),
    "commence_time": dt(e.get("commence_time")).isoformat() if dt(e.get("commence_time")) else None,
    "provider_event_id": str(e.get("id", "")), "provider": "The Odds API v4", "provider_region": REGION,
    "market_key": "h2h", "line": None, "settlement_rules_status": "unverified",
    "model_generated_at": model_generated_at,
    "model_pipeline_version": model_pipeline_version or (model["explanation"].get("pipeline_version") if isinstance(model.get("explanation"), dict) else None),
    "model_method": model["explanation"].get("method_version") if isinstance(model.get("explanation"), dict) else None,
    "description": "International observation; exact RO offer and settlement rules unverified",
    "verified_ro_offer": False, "ready_to_bet": False, "model_is_validated": False,
    "value_blockers": value_blockers()})
 return offers, parsed, len(seen_books)

def build_observations(events, fixtures, league, now, model_generated_at=None, model_pipeline_version=None):
 offers, matches, books = [], 0, set()
 seen_events = set()
 for e in events:
  if not isinstance(e, dict):
   continue
  f = match_event(e, [v for v in fixtures if isinstance(v, dict) and v.get("league") == league], now)
  if f is None:
   continue
  event_key = runner.key(f)
  if event_key in seen_events:
   continue
  seen_events.add(event_key)
  matches += 1
  one, _, _ = analyze_fixture(e, f, now, model_generated_at, model_pipeline_version)
  offers.extend(one)
  books.update(v["bookmaker_id"] for v in one)
 return offers, matches, books

def coherent_snapshots(offers):
 """Complete 1X2 from one book in one scan; never splice across scans."""
 snapshots = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
 reasons = Counter()
 for row in offers if isinstance(offers, list) else []:
  if not isinstance(row, dict):
   reasons["malformed_observation"] += 1
   continue
  try:
   stamp = dt(row.get("observed_at"))
   if stamp is None or row.get("outcome") not in OUTCOMES or not finite_number(row.get("odds"), 1.01, 1000):
    raise ValueError()
   if not finite_number(row.get("model_probability"), 0, 1) or not isinstance(row.get("bookmaker_id"), str) or not row["bookmaker_id"]:
    raise ValueError()
   if row.get("market_key", "h2h") != "h2h" or row.get("line") is not None:
    raise ValueError()
   if any(row.get(field) is not None and not isinstance(row[field], str) for field in ("quote_timestamp", "commence_time", "model_generated_at", "model_pipeline_version", "settlement_rules_status")):
    raise ValueError()
   start = dt(row.get("commence_time"))
   quote = dt(row.get("quote_timestamp"))
   if start and stamp >= start:
    raise ValueError()
   if row.get("quote_timestamp") is not None and (quote is None or not 0 <= (stamp-quote).total_seconds() <= FRESH_MAX_MINUTES*60):
    raise ValueError()
   if not all(isinstance(row.get(field), str) and row[field].strip() for field in ("league", "date", "home", "away")):
    raise ValueError()
   if date.fromisoformat(row["date"]).isoformat() != row["date"]:
    raise ValueError()
   event = (row["league"], row["date"], runner.norm(row["home"]), runner.norm(row["away"]))
   if event[0] not in SPORTS or not event[2] or not event[3] or event[2] == event[3]:
    raise ValueError()
   snapshots[event][stamp][row["bookmaker_id"]].append(row)
  except (KeyError, ValueError, TypeError, OverflowError):
   reasons["invalid_observation_or_timestamp"] += 1
 return snapshots, reasons

def cross_book_consensus(offers):
 """Historical plausibility diagnostic, on latest coherent scan per event.

 Distinct IDs are not proof of independent bookmaker ownership. Legacy records
 without original source timestamps remain explicitly historical diagnostics.
 """
 snapshots, reasons = coherent_snapshots(offers)
 diagnostics, flagged, used_stamps = [], [], []
 for event, scans in snapshots.items():
  stamp = max(scans)
  valid = []
  model_reference = None
  for book_id, rows in scans[stamp].items():
   market = {}
   conflict = False
   for row in rows:
    outcome = row["outcome"]
    if outcome in market and row != market[outcome]:
     conflict = True
    market[outcome] = row
   if conflict or set(market) != set(OUTCOMES):
    reasons["incomplete_or_conflicting_market"] += 1
    continue
   model = {k: market[k]["model_probability"] for k in OUTCOMES}
   metadata = {(r.get("quote_timestamp"), r.get("commence_time"), r.get("model_generated_at"), r.get("model_pipeline_version"), r.get("settlement_rules_status")) for r in market.values()}
   if not valid_probabilities(model) or len(metadata) != 1:
    reasons["inconsistent_model_or_quote_metadata"] += 1
    continue
   model_identity = (model, market["home"].get("model_pipeline_version"))
   if model_reference is not None and model_identity != model_reference:
    reasons["mixed_model_snapshots"] += 1
    continue
   den = sum(1/r["odds"] for r in market.values())
   if not .94 <= den <= 1.18:
    reasons["extreme_bookmaker_margin"] += 1
    continue
   model_reference = model_identity
   valid.append((book_id, {k: (1/v["odds"])/den for k, v in market.items()}, market))
  if len(valid) < 3:
   reasons["insufficient_distinct_bookmaker_ids"] += 1
   continue
  median = {k: statistics.median(probs[k] for _, probs, _ in valid) for k in OUTCOMES}
  den = sum(median.values())
  median = {k: v/den for k, v in median.items()}
  each = valid[0][2]
  model = {k: each[k]["model_probability"] for k in OUTCOMES}
  drift = max(abs(model[k]-median[k]) for k in OUTCOMES)
  spread = max(max(probs[k] for _, probs, _ in valid)-min(probs[k] for _, probs, _ in valid) for k in OUTCOMES)
  if drift >= .10:
   reason = "model_market_disagreement"
  elif spread >= .12:
   reason = "books_disagree"
  elif any(r.get("model_low_sample", True) for r in each.values()):
   reason = "model_sample_insufficient"
  else:
   reason = "unverified_model_and_unverified_ro_prices"
  reasons[reason] += 1
  used_stamps.append(stamp)
  diagnostic = {"league": event[0], "date": event[1], "home": each["home"]["home"], "away": each["home"]["away"],
   "books": len(valid), "bookmaker_independence_verified": False,
   "observed_at": stamp.isoformat(), "historical_snapshot_only": True,
   "source_timestamps_complete": all(r.get("quote_timestamp") for _, _, m in valid for r in m.values()),
   "max_model_consensus_gap_pp": round(drift*100, 1), "max_cross_book_spread_pp": round(spread*100, 1),
   "model_probabilities": model, "market_consensus_no_vig": {k: round(v, 5) for k, v in median.items()},
   "reason": reason, "verified_value": False, "value_blockers": value_blockers()}
  diagnostics.append(diagnostic)
  if reason == "model_market_disagreement":
   flagged.append({"match": event[0]+" "+diagnostic["home"]+" — "+diagnostic["away"], "gap_pp": round(drift*100, 1)})
 diagnostics.sort(key=lambda row: row["max_model_consensus_gap_pp"], reverse=True)
 return {"status": "diagnostic_only_no_verified_value", "reason_counts": dict(reasons),
  "data_timestamp": max(used_stamps).isoformat() if used_stamps else None,
  "market_events_evaluated": len(diagnostics), "large_model_disagreements": len(flagged),
  "largest_disagreements": flagged[:10], "items": diagnostics[:100],
  "recommendation": "Nu există pariuri value verificate.", "value_blockers": value_blockers()}

def budget_state(budget, now):
 """Missing/corrupt counters must never reset the spending guard."""
 if not isinstance(budget, dict):
  return None
 month = budget.get("month")
 if not isinstance(month, str) or not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", month) or month > now.strftime("%Y-%m"):
  return None
 for name in ("spent", "calls"):
  value = budget.get(name)
  if not isinstance(value, int) or isinstance(value, bool) or value < 0:
   return None
 remaining = budget.get("provider_reported_remaining")
 if remaining is not None and (not isinstance(remaining, int) or isinstance(remaining, bool) or remaining < 0):
  return None
 if month != now.strftime("%Y-%m"):
  return {"month": now.strftime("%Y-%m"), "spent": 0, "calls": 0, "provider_reported_remaining": None, "limit": MAX_MONTHLY, "accounting": "conservative_request_reservations"}
 return {**budget, "limit": MAX_MONTHLY, "accounting": "conservative_request_reservations"}

def fetch_scan():
 OUT.mkdir(parents=True, exist_ok=True)
 close_watchlist("scan_started")
 key = os.getenv("ODDS_API_KEY", "").strip()
 now = datetime.now(timezone.utc)
 if not key:
  status("needs_api_key", message="Cheia lipsește; nicio cerere efectuată.")
  return 0
 latest = read_json("latest.json", None)
 generated = dt(latest.get("generated_at")) if isinstance(latest, dict) else None
 if not generated or not 0 <= (now-generated).total_seconds() <= 12*3600:
  status("stale_model", message="Model lipsă, vechi sau timestamp invalid; nicio cotă solicitată.")
  return 0
 fixtures = latest.get("fixtures", [])
 if not isinstance(fixtures, list) or not fixtures:
  status("missing_fixtures", message="Nu există meciuri; nicio cotă solicitată.")
  return 0
 eligible = []
 for f in fixtures:
  if not isinstance(f, dict):
   continue
  kickoff = runner.fixture_kickoff(f)
  markets = f.get("markets")
  goals = markets.get("goals") if isinstance(markets, dict) else None
  if kickoff and kickoff > now and isinstance(goals, dict) and valid_probabilities(goals.get("h2h")) and runner.comparison_allowed(goals,now):
   eligible.append(f)
 fixtures = eligible
 if not fixtures:
  status("missing_fixtures", message="Nu există meciuri viitoare cu oră, probabilități valide și istoric recent verificabil.")
  return 0
 budget = budget_state(read_json("odds_budget.json", None), now)
 if budget is None:
  status("budget_invalid", message="Buget lipsă sau corupt; scannerul este blocat.")
  return 0
 remaining = budget.get("provider_reported_remaining")
 if budget["spent"]+MAX_PER_SCAN > MAX_MONTHLY or (remaining is not None and remaining < MIN_RESERVE+1):
  status("budget_guard", spent=budget["spent"], limit=MAX_MONTHLY, message="Limită de credit sau rezervă atinsă.")
  return 0
 offers, raw_events, matched, errors, books = [], 0, 0, [], set()
 used = 0
 for league, sport in SPORTS.items():
  if budget["spent"] >= MAX_MONTHLY or used >= MAX_PER_SCAN or (remaining is not None and remaining < MIN_RESERVE+1):
   break
  if not any(f.get("league") == league for f in fixtures):
   continue
  # Persist one conservative credit before the request, also on timeout/crash.
  budget["spent"] += 1
  budget["calls"] += 1
  used += 1
  if remaining is not None:
   remaining -= 1
  budget["provider_reported_remaining"] = remaining
  write_json("odds_budget.json", budget)
  params = urlencode({"apiKey": key, "regions": REGION, "markets": "h2h", "oddsFormat": "decimal", "dateFormat": "iso"})
  results, headers, error = get_json(f"https://api.the-odds-api.com/v4/sports/{sport}/odds/?{params}")
  hdr = {str(k).lower(): v for k, v in headers.items()}
  try:
   cost = max(1, int(hdr.get("x-requests-last", 1)))
  except (ValueError, TypeError):
   cost = 1
  budget["spent"] += cost-1
  used += cost-1
  try:
   reported = int(hdr["x-requests-remaining"])
   if reported >= 0:
    remaining = reported
  except (KeyError, ValueError, TypeError):
   pass
  budget["provider_reported_remaining"] = remaining
  write_json("odds_budget.json", budget)
  if error:
   errors.append({"league": league, "error": error})
   if any(str(code) in error for code in (401, 403, 429)):
    break
   continue
  if not isinstance(results, list):
   errors.append({"league": league, "error": "Unexpected odds payload"})
   continue
  raw_events += len(results)
  # Receipt time, not scan start: a quote can update or a match can start
  # while the request is in flight. Never backdate prospective evidence.
  received_at = datetime.now(timezone.utc)
  one, count, found_books = build_observations(results, fixtures, league, received_at, generated.isoformat(), latest.get("pipeline_version"))
  matched += count
  offers.extend(one)
  books.update(found_books)
 prior = read_json("odds_observations.json", [])
 if not isinstance(prior, list):
  prior = []
 # Keep whole scan snapshots. Slicing arbitrary rows can split a 1X2 market.
 combined = prior+offers
 if len(combined) > 6000:
  stamps = sorted({r.get("observed_at", "") for r in combined if isinstance(r, dict)}, reverse=True)
  keep, total = set(), 0
  for stamp in stamps:
   size = sum(isinstance(r, dict) and r.get("observed_at", "") == stamp for r in combined)
   if total and total+size > 6000:
    break
   keep.add(stamp)
   total += size
  combined = [r for r in combined if isinstance(r, dict) and r.get("observed_at", "") in keep]
 write_json("odds_observations.json", combined)
 consensus = cross_book_consensus(offers)
 write_json("odds_diagnostics.json", {"generated_at": datetime.now(timezone.utc).isoformat(), **consensus})
 state = "connected" if offers and not errors else "partial" if offers else "api_error" if errors else "no_valid_quotes" if raw_events else "no_events"
 close_watchlist(state)
 source_dates = [r["quote_timestamp"] for r in offers]
 source_timestamp = max(source_dates) if source_dates else None
 status(state, api_events=raw_events, matched_games=matched, books_responding=sorted(books),
  evaluated_prices=len(offers), model_disagreements=consensus["large_model_disagreements"],
  events_consensus_checked=consensus["market_events_evaluated"], new_observations=len(offers),
  total_historical_observations=len(combined), spent_this_month=budget["spent"], provider_remaining=remaining,
  data_timestamp=source_timestamp, last_successful_quote_at=source_timestamp, errors=errors,
  message="Observații internaționale; nicio ofertă românească verificată.")
 print(f"Odds scan {state}: {raw_events} events, {matched} matched, {len(offers)} diagnostic prices. Conservatively accounted API units {used}.")
 return 0

def selftest():
 now = datetime(2026, 11, 6, 17, tzinfo=timezone.utc)
 fixture = {"league": "Premier League", "date": "2026-11-07", "time": "16:00", "home": "Arsenal", "away": "Chelsea",
  "markets": {"goals": {"h2h": {"home": .5, "draw": .25, "away": .25}, "n_home": 20, "n_away": 20, "small_sample": False,
    "explanation": {"last_observation_date": "2026-11-04"}}}}
 event = {"home_team": "Arsenal FC", "away_team": "Chelsea", "commence_time": "2026-11-07T15:00:00Z", "bookmakers": [
  {"key": "test", "title": "Test source", "last_update": "2026-11-06T16:50:00Z", "markets": [{"key": "h2h", "outcomes": [
   {"name": "Arsenal FC", "price": 2.15}, {"name": "Draw", "price": 3.4}, {"name": "Chelsea", "price": 3.5}]}]}]}
 assert match_event(event, [fixture], now) is fixture
 assert match_event({**event, "away_team": "Liverpool"}, [fixture], now) is None
 assert match_event({**event, "commence_time": "2026-11-07T16:00:00Z"}, [fixture], now) is None
 offers, count, _ = analyze_fixture(event, fixture, now)
 assert len(offers) == 3 and count == 1 and all(not r["ready_to_bet"] for r in offers)
 assert dt("2026-11-06T17:00:00") is None
 assert not valid_probabilities({"home": .8, "draw": .3, "away": .2})
 assert value_blockers({"ready_to_bet": True, "verified_ro_offer": True, "model_is_validated": True})
 print("Odds adapter self-tests passed.")

if __name__ == "__main__":
 sys.exit((selftest() or 0) if "--self-test" in sys.argv else fetch_scan())
