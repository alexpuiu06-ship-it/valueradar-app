#!/usr/bin/env python3
"""ValueRadar Elo challenger: isolated, explainable, chronological 1X2 model.

Never auto-promote the challenger to production, and never derive betting
recommendations from the mere disagreement of Elo and a bookmaker.
"""
from __future__ import annotations
import json,math,sys
from itertools import groupby
from collections import defaultdict
from datetime import datetime,timezone,date,timedelta
from pathlib import Path
import runner

OUT=Path(__file__).resolve().parent/"docs"
CANDIDATES={
 "elo_fast":{"k":35,"scale":320,"home_advantage":65,"draw_strength":.75},
 "elo_balanced":{"k":22,"scale":350,"home_advantage":70,"draw_strength":.78},
 "elo_conservative":{"k":17,"scale":400,"home_advantage":75,"draw_strength":.72},
 "elo_strong_favorites":{"k":24,"scale":290,"home_advantage":55,"draw_strength":.8}}
BASE=1500.
RETURN_FACTOR=.82
def season(d):
 day=date.fromisoformat(d)
 return day.year if day.month>=7 else day.year-1
def probs(home,away,params):
 delta=max(-650.,min(650.,home-away+params["home_advantage"]))
 x=10**(delta/(2*params["scale"]))
 a=1/x
 draw=params["draw_strength"]
 z=x+a+draw
 return {"home":x/z,"draw":draw/z,"away":a/z}
def expected_points(p):
 return p["home"]+.5*p["draw"]
def result(h,a):
 if h>a:return "home"
 if h<a:return "away"
 return "draw"
def logloss(p,y):
 return -math.log(max(1e-8,p[y]))
def brier(p,y):
 return sum((p[k]-(1. if k==y else 0.))**2 for k in ("home","draw","away"))/3.
def process(rows,params,upcoming=None):
 """Sequential ratings updated only after all matches of same date are predicted."""
 rows=sorted(rows,key=lambda r:r["date"])
 ratings={}
 games_played=defaultdict(int)
 history={}
 prior_season=None
 for day,generator in groupby(rows,key=lambda r:r["date"]):
  current=season(day)
  if prior_season is not None and current!=prior_season:
   ratings={team:BASE+(rating-BASE)*RETURN_FACTOR for team,rating in ratings.items()}
  prior_season=current
  batch=list(generator);pending=[]
  for m in batch:
   home=runner.norm(m["home"]);away=runner.norm(m["away"])
   rh=ratings.get(home,BASE);ra=ratings.get(away,BASE)
   distribution=probs(rh,ra,params)
   event=(m["league"],m["date"],home,away)
   history[event]={"p":distribution,"y":result(m["gh"],m["ga"]),
    "rating_home":rh,"rating_away":ra,
    "games_home":games_played[home],"games_away":games_played[away]}
   score=1. if m["gh"]>m["ga"] else .5 if m["gh"]==m["ga"] else 0.
   delta=params["k"]*(score-expected_points(distribution))
   pending.append((home,away,delta))
  for home,away,delta in pending:
   ratings[home]=ratings.get(home,BASE)+delta
   ratings[away]=ratings.get(away,BASE)-delta
   games_played[home]+=1
   games_played[away]+=1
 predictions={}
 for m in upcoming or []:
  home=runner.norm(m["home"]);away=runner.norm(m["away"])
  rh=ratings.get(home,BASE);ra=ratings.get(away,BASE)
  out=probs(rh,ra,params)
  predictions[(m["league"],m["date"],home,away)]={
   "home":m["home"],"away":m["away"],"league":m["league"],"date":m["date"],
   "probabilities":{k:round(v,5) for k,v in out.items()},
   "rating_home":round(rh,1),"rating_away":round(ra,1),
   "games_home":games_played[home],"games_away":games_played[away],
   "low_sample":min(games_played[home],games_played[away])<8,
   "rating_difference_including_home_advantage":round(rh-ra+params["home_advantage"],1),
   "parameters":params,"status":"CHALLENGER_ONLY_not_a_betting_recommendation"}
 return history,predictions
def evaluate(hist,fixtures):
 markets={}
 all_predictions={}
 today=datetime.now(timezone.utc).date().isoformat()
 horizon=(datetime.now(timezone.utc).date()+timedelta(days=30)).isoformat()
 configs={k:[] for k in CANDIDATES}
 for league in runner.LEAGUES:
  rows=sorted([r for r in hist if r["league"]==league and r.get("gh") is not None and r.get("ga") is not None],key=lambda r:r["date"])
  upcoming=[f for f in fixtures if f["league"]==league and today<=f["date"]<=horizon]
  pred_by={}
  live_by={}
  for name,params in CANDIDATES.items():
   pred_by[name],live_by[name]=process(rows,params,upcoming)
  n=len(rows)
  val_start=max(70,int(n*.55))
  holdout_start=max(val_start+1,int(n*.78))
  for i,m in enumerate(rows):
   if i<val_start:continue
   event=(m["league"],m["date"],runner.norm(m["home"]),runner.norm(m["away"]))
   if any(event not in pred_by[k] for k in CANDIDATES):continue
   entry={"league":league,"date":m["date"],"y":result(m["gh"],m["ga"]),
    "split":"validation" if i<holdout_start else "holdout"}
   for name in CANDIDATES:
    entry[name]=pred_by[name][event]["p"]
   if i>=holdout_start:
    original=runner.pred(rows[:i],m,"goals")
    entry["current_poisson"]=original["h2h"] if original else None
   markets.setdefault(league,[]).append(entry)
  for name in CANDIDATES:
   for k,record in live_by[name].items():
    all_predictions.setdefault(name,[]).append(record)
 validation=[]
 for name in CANDIDATES:
  selected=[e for records in markets.values() for e in records if e["split"]=="validation"]
  scores=[logloss(e[name],e["y"]) for e in selected]
  validation.append((sum(scores)/len(scores) if scores else float("inf"),name,len(scores)))
 validation.sort()
 winner=validation[0][1]
 scores_by_league={}
 pair_gains=[]
 for league,records in markets.items():
  testing=[e for e in records if e["split"]=="holdout" and e.get("current_poisson")]
  elo_losses=[logloss(e[winner],e["y"]) for e in testing]
  old_losses=[logloss(e["current_poisson"],e["y"]) for e in testing]
  diffs=[a-b for a,b in zip(old_losses,elo_losses)]
  pair_gains+=diffs
  scores_by_league[league]={"n":len(diffs),
   "elo_logloss":round(sum(elo_losses)/len(elo_losses),5) if diffs else None,
   "current_logloss":round(sum(old_losses)/len(old_losses),5) if diffs else None,
   "mean_gain":round(sum(diffs)/len(diffs),5) if diffs else None}
 n=len(pair_gains)
 gain=sum(pair_gains)/n if n else None
 interval=None
 if n>=3:
  std=(sum((v-gain)**2 for v in pair_gains)/(n-1))**.5
  half=1.96*std/math.sqrt(n)
  interval=[round(gain-half,5),round(gain+half,5)]
 return {"generated_at":datetime.now(timezone.utc).isoformat(),
   "status":"RESEARCH_ONLY_NOT_PROMOTED",
   "rating_method":"Davidson three-outcome Elo; points update on result after each match date",
   "selection":"candidate chosen by validation log-loss, holdout not used for selection",
   "candidates":CANDIDATES,
   "best_candidate":winner,
   "validation_scores":[{"model":name,"logloss":round(score,5),"n":n} for score,name,n in validation],
   "holdout":{"n":n,"logloss_gain_vs_current":round(gain,5) if gain is not None else None,
     "approx_95_ci":interval,"by_league":scores_by_league},
   "limitations":["Elo data starts 2024/25; no player/team sheet or referee inputs",
     "Team name matching is imperfect","Approximately normal interval assumes independent matches",
     "No historical odds were used for selection","No profit validation"],
   "live_research_only":all_predictions.get(winner,[])}
def market_diagnostic(result,prior):
 """Snapshot diagnostic only. It does NOT validate the model or a value edge."""
 if not isinstance(prior,dict):return None
 look={(x["league"],x["date"],x["home"],x["away"]):x for x in result.get("live_research_only",[])}
 observations=[]
 for entry in prior.get("items",[]):
  event=(entry["league"],entry["date"],entry["home"],entry["away"])
  elo=look.get(event)
  if not elo:continue
  market=entry.get("market_consensus_no_vig",{})
  old=entry.get("model_probabilities",{})
  if set(market)!={"home","draw","away"} or set(old)!={"home","draw","away"}:continue
  old_gap=max(abs(old[k]-market[k]) for k in ("home","draw","away"))
  new_gap=max(abs(elo["probabilities"][k]-market[k]) for k in ("home","draw","away"))
  observations.append({"league":entry["league"],"date":entry["date"],
    "home":entry["home"],"away":entry["away"],
    "books":entry.get("books",0),
    "poisson_largest_gap_pp":round(old_gap*100,2),
    "elo_largest_gap_pp":round(new_gap*100,2),
    "improvement_pp":round((old_gap-new_gap)*100,2),
    "market_no_vig":market,"poisson":old,"elo":elo["probabilities"],
    "rating_home":elo["rating_home"],"rating_away":elo["rating_away"],
    "elo_low_sample":elo.get("low_sample",True)})
 n=len(observations)
 if not n:return {"n":0,"note":"No matching bookmaker consensus snapshots; not a source of truth."}
 return {"n":n,"source":"Previously stored international bookmaker no-vig consensus snapshots",
   "snapshot_timestamp":prior.get("data_timestamp") or prior.get("generated_at"),
   "status":"descriptive_diagnostic_not_outcome_validation",
   "mean_largest_gap_pp_current":round(sum(x["poisson_largest_gap_pp"] for x in observations)/n,2),
   "mean_largest_gap_pp_elo":round(sum(x["elo_largest_gap_pp"] for x in observations)/n,2),
   "large_10pp_current":sum(x["poisson_largest_gap_pp"]>=10 for x in observations),
   "large_10pp_elo":sum(x["elo_largest_gap_pp"]>=10 for x in observations),
   "events":sorted(observations,key=lambda x:x["poisson_largest_gap_pp"],reverse=True)[:100],
   "warning":"The odds consensus is not objective ground truth; this is not a betting profitability test."}

def selftest():
 config=CANDIDATES["elo_balanced"]
 p=probs(1500,1500,config)
 assert abs(sum(p.values())-1)<1e-12
 assert probs(1650,1450,config)["home"]>p["home"]
 assert probs(1450,1650,config)["away"]>p["away"]
 rows=[{"league":"Premier League","date":"2026-08-01","home":"Team A","away":"Team B","gh":2,"ga":0},
       {"league":"Premier League","date":"2026-08-01","home":"Team C","away":"Team D","gh":0,"ga":2},
       {"league":"Premier League","date":"2026-08-10","home":"Team A","away":"Team C","gh":3,"ga":0}]
 history,upcoming=process(rows,config,[{"league":"Premier League","date":"2026-08-15","home":"Team A","away":"Team B"}])
 first=history[("Premier League","2026-08-01",runner.norm("Team A"),runner.norm("Team B"))]
 assert first["rating_home"]==BASE
 assert len(history)==3
 assert len(upcoming)==1
 mocked={"live_research_only":[{
   **list(upcoming.values())[0],"league":"Premier League",
   "date":"2026-08-15","home":"Team A","away":"Team B"}]}
 p=market_diagnostic(mocked,{"items":[{"league":"Premier League","date":"2026-08-15",
   "home":"Team A","away":"Team B","books":4,
   "market_consensus_no_vig":{"home":.45,"draw":.25,"away":.30},
   "model_probabilities":{"home":.60,"draw":.25,"away":.15}}]})
 assert p["n"]==1 and p["mean_largest_gap_pp_current"]==15
 print("Elo challenger tests passed.")
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 hist,fixtures,report=runner.load_all()
 if len(hist)<100:raise SystemExit("Insufficient historical data; old Elo report untouched.")
 out=evaluate(hist,fixtures)
 try:
  previously=json.loads((OUT/"odds_diagnostics.json").read_text(encoding="utf-8"))
 except (OSError,ValueError):previously=None
 out["market_diagnostic"]=market_diagnostic(out,previously)
 (OUT/"elo_challenger.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
 print("Elo holdout:",out["holdout"]["n"],"candidate",out["best_candidate"],"gain",out["holdout"]["logloss_gain_vs_current"])
if __name__=="__main__":
 if "--self-test" in sys.argv:selftest()
 else:main()
