#!/usr/bin/env python3
"""ValueRadar: real pre-match odds adapter for The Odds API v4.

NO mock data in production, NO automatic betting, NO unfounded ROI claims.
Key comes ONLY from ODDS_API_KEY environment / GitHub Actions secret.
"""
from __future__ import annotations
import json, math, os, sys, urllib.request, urllib.error
from collections import Counter
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher
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
 "realbetisbalompie":"realbetis","realbetis":"realbetis",
 "athletic":"athleticbilbao","borussiamgladbach":"monchengladbach"
}
def canonical(name):
 text=runner.norm(name)
 return ALIASES.get(text,text)
def dt(value):
 try:
  d=datetime.fromisoformat(str(value).replace("Z","+00:00"))
  return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
 except (ValueError, TypeError):return None
def get_json(url):
 # URL includes key. Avoid printing/logging URLs or uncaught errors containing query params.
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={
   "User-Agent":"ValueRadar-educational-odds/0.1"}),timeout=16) as res:
   return json.loads(res.read(3000000).decode("utf8")),dict(res.headers.items()),None
 except urllib.error.HTTPError as exc:
  return [],{},f"API HTTP {exc.code} (verifică abonamentul, cheia și creditul)"
 except Exception as exc:
  return [],{},f"Network/API error: {type(exc).__name__}"
def read_json(name,default):
 try:return json.loads((OUT/name).read_text(encoding="utf-8"))
 except (FileNotFoundError,ValueError,TypeError):return default
def write_json(name,data):
 OUT.mkdir(parents=True,exist_ok=True)
 (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
def status(mode,**details):
 s={"status":mode,"checked_at":datetime.now(timezone.utc).isoformat(),
    "provider":"The Odds API v4","region":REGION,"market":"h2h",
    "bookmakers_ro_confirmed":False,"bookmakers_ro_requested":TARGET_BOOKS,
    "note":"Only international data is monitored until exact Romanian bookmaker feeds are verified.",
    **details}
 write_json("odds_status.json",s)
 return s
def match_event(e,fixtures,now):
 home,away=canonical(e.get("home_team","")),canonical(e.get("away_team",""))
 start=dt(e.get("commence_time"))
 if not start or start<=now or start>now+timedelta(days=30):return None
 matches=[]
 for f in fixtures:
  kickoff=runner.fixture_kickoff(f)
  if not kickoff or abs((start-kickoff).total_seconds())>3*3600:continue
  fh,fa=canonical(f["home"]),canonical(f["away"])
  sh=SequenceMatcher(None,home,fh).ratio()
  sa=SequenceMatcher(None,away,fa).ratio()
  if home==fh and away==fa:score=1.
  elif min(sh,sa)>=.88:score=(sh+sa)/2
  else:continue
  matches.append((score,f))
 if not matches:return None
 matches.sort(key=lambda x:x[0],reverse=True)
 if len(matches)>1 and matches[0][0]-matches[1][0]<.05:return None
 return matches[0][1]
def parse_h2h(bookmaker,event,now):
 all_outcomes=[]
 for market in bookmaker.get("markets",[]):
  if market.get("key")=="h2h":
   all_outcomes=market.get("outcomes",[])
   source_update=dt(market.get("last_update")) or dt(bookmaker.get("last_update"))
   break
 if not all_outcomes:return None
 prices={}
 for item in all_outcomes:
  name=item.get("name","")
  p=item.get("price")
  if not isinstance(p,(int,float)) or not math.isfinite(p) or p<=1.005:continue
  outcome="draw" if str(name).casefold() in ("draw","tie","x") else (
      "home" if canonical(name)==canonical(event.get("home_team","")) else
      "away" if canonical(name)==canonical(event.get("away_team","")) else None)
  if outcome:
   if outcome in prices:return None
   prices[outcome]=float(p)
 if set(prices)!={"home","draw","away"}:return None
 overround=sum(1/x for x in prices.values())
 if not .85<=overround<=1.5:return None
 if source_update is None:return None
 age=(now-source_update).total_seconds()/60
 if age< -10 or age>FRESH_MAX_MINUTES:return None
 return prices,round(overround-1,5),round(max(age,0),1)
def analyze_fixture(e,f,now):
 model=(f.get("markets",{}).get("goals") or {})
 probs=model.get("h2h")
 if not probs:return [],0,0
 sample_ok=not bool(model.get("small_sample")) and min(model.get("n_home",0),model.get("n_away",0))>=8
 parsed=0;seen_books=set();offers=[]
 for book in e.get("bookmakers",[]):
  quote=parse_h2h(book,e,now)
  if not quote:continue
  prices,margin,age=quote
  parsed+=1
  key=str(book.get("key","unknown"))
  seen_books.add(key)
  den=sum(1/v for v in prices.values())
  for outcome,odd in prices.items():
   p=float(probs[outcome])
   implied=(1/odd)/den
   ev=p*odd-1
   offers.append({"league":f["league"],"date":f["date"],"home":f["home"],"away":f["away"],
    "bookmaker":str(book.get("title","Unknown")),"bookmaker_id":key,
    "outcome":outcome,"odds":round(odd,3),
    "model_probability":round(p,5),"market_probability_no_vig":round(implied,5),
    "estimated_ev":round(ev,5),"price_margin":margin,
    "quote_age_minutes":age,"model_low_sample":not sample_ok,
    "description":"International bookmaker, not verified Romanian market",
    "verified_ro_offer":False,"ready_to_bet":False})
 return offers,parsed,len(seen_books)
def build_observations(events,fixtures,league,now):
 offers=[];matches=0;books=set()
 for e in events:
  f=match_event(e,[v for v in fixtures if v.get("league")==league],now)
  if f is None:continue
  matches+=1
  oo,valid,_=analyze_fixture(e,f,now)
  offers+=oo
  books.update(v["bookmaker_id"] for v in oo)
 return offers,matches,books
def fetch_scan():
 OUT.mkdir(parents=True,exist_ok=True)
 key=os.getenv("ODDS_API_KEY","").strip()
 now=datetime.now(timezone.utc)
 if not key:
  status("needs_api_key",message="Cheia ODDS_API_KEY lipsește din GitHub Actions Secrets. Scannerul nu a efectuat nicio cerere.")
  return 0
 latest=read_json("latest.json",{})
 fixtures=latest.get("fixtures",[])
 if not fixtures:
  status("missing_fixtures",message="Nu există meciuri în latest.json; cotele nu au fost solicitate.")
  return 0
 budget=read_json("odds_budget.json",{})
 month=now.strftime("%Y-%m")
 spent=budget.get("spent",0) if budget.get("month")==month else 0
 total_calls=budget.get("calls",0) if budget.get("month")==month else 0
 if spent+MAX_PER_SCAN>MAX_MONTHLY:
  status("budget_guard",spent=spent,limit=MAX_MONTHLY,message="Bugetul lunar automat al API a fost atins. Nicio interogare nouă.")
  return 0
 nowstamp=now.isoformat();offers=[];raw_events=0;matched=0;errors=[];used=0;remaining=None;books=set()
 for league,sport in SPORTS.items():
  if spent+used>=MAX_MONTHLY:break
  if remaining is not None and remaining<MIN_RESERVE:break
  if not any(f.get("league")==league for f in fixtures):continue
  params=urlencode({"apiKey":key,"regions":REGION,"markets":"h2h","oddsFormat":"decimal",
    "dateFormat":"iso"})
  uri=f"https://api.the-odds-api.com/v4/sports/{sport}/odds/?{params}"
  results,headers,error=get_json(uri)
  if error:
   errors.append({"league":league,"error":error})
   if "401" in error or "403" in error or "429" in error:break
   continue
  if not isinstance(results,list):
   errors.append({"league":league,"error":"Unexpected odds payload"})
   continue
  raw_events+=len(results)
  one,m,b=build_observations(results,fixtures,league,now)
  matched+=m;offers+=one;books.update(b)
  hdr={k.lower():v for k,v in headers.items()}
  try:cost=int(hdr.get("x-requests-last","1" if results else "0"))
  except ValueError:cost=1 if results else 0
  used+=max(0,cost)
  try:remaining=int(hdr.get("x-requests-remaining"))
  except (TypeError,ValueError):pass
  total_calls+=1
 spent+=used
 write_json("odds_budget.json",{"month":month,"spent":spent,"calls":total_calls,
  "limit":MAX_MONTHLY,"provider_reported_remaining":remaining})
 # Small derived snapshots only; not an API resale or a raw data dump.
 prior=read_json("odds_observations.json",[])
 if not isinstance(prior,list):prior=[]
 newobs=[]
 for v in offers:
  newobs.append({**v,"observed_at":nowstamp})
 prior.extend(newobs)
 prior=prior[-2200:]
 write_json("odds_observations.json",prior)
 watch=sorted([r for r in offers if r["estimated_ev"]>.02],key=lambda x:x["estimated_ev"],reverse=True)[:60]
 write_json("odds_watchlist.json",{"generated_at":nowstamp,
  "provider":"The Odds API v4", "region":REGION,"live_ro_supported":False,
  "status":"price_discrepancies_unverified",
  "recommendation":"NO BET — model not validated and Romanian bookmaker prices not available.",
  "items":watch})
 state="connected" if raw_events>0 and not errors else ("partial" if raw_events>0 else ("api_error" if errors else "no_events"))
 status(state,api_events=raw_events,matched_games=matched,books_responding=sorted(books),
  evaluated_prices=len(offers),watchlist_count=len(watch),
  new_observations=len(newobs),total_historical_observations=len(prior),
  spent_this_month=spent,provider_remaining=remaining,errors=errors,
  message="Real provider data; matched prices are NOT confirmed Romanian bookmaker quotes.")
 print(f"Odds scan {state}: {raw_events} provider fixtures, {matched} matched, {len(offers)} derived comparisons. API units {used}.")
 return 0
def selftest():
 from datetime import timedelta
 now=datetime(2026,11,6,17,tzinfo=timezone.utc)
 f={"league":"Premier League","date":"2026-11-07","time":"16:00",
    "home":"Arsenal","away":"Chelsea","markets":{"goals":{
    "h2h":{"home":.5,"draw":.25,"away":.25},"n_home":20,"n_away":20,"small_sample":False}}}
 e={"home_team":"Arsenal FC","away_team":"Chelsea",
    "commence_time":"2026-11-07T15:00:00Z",
    "bookmakers":[{"key":"test","title":"Test source","last_update":"2026-11-06T16:50:00Z",
      "markets":[{"key":"h2h","last_update":"2026-11-06T16:50:00Z",
       "outcomes":[{"name":"Arsenal FC","price":2.15},{"name":"Draw","price":3.4},{"name":"Chelsea","price":3.5}]}]}]}
 assert match_event(e,[f],now) is f
 assert match_event({**e,"away_team":"Liverpool"},[f],now) is None
 assert match_event({**e,"commence_time":"2026-11-07T04:00:00Z"},[f],now) is None
 o,n,b=analyze_fixture(e,f,now)
 assert n==1 and len(o)==3
 assert next(x for x in o if x["outcome"]=="home")["estimated_ev"]>0
 assert all(x["ready_to_bet"] is False for x in o)
 e["bookmakers"][0]["markets"][0]["outcomes"][0]["price"]=0
 assert parse_h2h(e["bookmakers"][0],e,now) is None
 print("Odds adapter self-tests passed.")
if __name__=="__main__":
 sys.exit((selftest() or 0) if "--self-test" in sys.argv else fetch_scan())
