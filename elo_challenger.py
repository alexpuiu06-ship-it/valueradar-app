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
import calibration

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
def process(rows,params,upcoming=None,as_of=None):
 """Predict a calendar day's matches before updating any result of that day.

 Upcoming can also contain past replay dates: those predictions receive ratings
 from strictly earlier dates, never the final ratings from the whole dataset.
 League is part of every rating key; off-season regression applies at prediction.
 """
 rows,_=calibration.prepare_history(rows,as_of)
 results_by_day=defaultdict(list);fixtures_by_day=defaultdict(list)
 for m in rows:results_by_day[m["date"]].append(m)
 for m in upcoming or []:
  try:
   if m["league"] not in runner.LEAGUES or not runner.norm(m["home"]) or runner.norm(m["home"])==runner.norm(m["away"]):continue
   if date.fromisoformat(m["date"]).isoformat()!=m["date"]:continue
   fixtures_by_day[m["date"]].append(m)
  except (TypeError,ValueError,KeyError):continue
 ratings={};games_played=defaultdict(int);history={};predictions={};prior_season={}
 for day in sorted(set(results_by_day)|set(fixtures_by_day)):
  batch=results_by_day[day];fixtures=fixtures_by_day[day]
  for league in {m["league"] for m in batch+fixtures}:
   current=season(day);previous=prior_season.get(league)
   if previous is not None and current>previous:
    factor=RETURN_FACTOR**(current-previous)
    ratings={team:BASE+(rating-BASE)*factor if team[0]==league else rating for team,rating in ratings.items()}
   prior_season[league]=current
  pending=[]
  tagged=[(False,m) for m in batch]+[(True,m) for m in fixtures]
  for is_fixture,m in sorted(tagged,key=lambda item:(runner.key(item[1]),item[0])):
   home=(m["league"],runner.norm(m["home"]));away=(m["league"],runner.norm(m["away"]))
   rh=ratings.get(home,BASE);ra=ratings.get(away,BASE)
   distribution=probs(rh,ra,params);event=runner.key(m)
   if not is_fixture:
    history[event]={"p":distribution,"y":result(m["gh"],m["ga"]),
     "rating_home":rh,"rating_away":ra,"games_home":games_played[home],"games_away":games_played[away]}
    score=1. if m["gh"]>m["ga"] else .5 if m["gh"]==m["ga"] else 0.
    pending.append((home,away,params["k"]*(score-expected_points(distribution))))
   else:
    predictions[event]={
     "home":m["home"],"away":m["away"],"league":m["league"],"date":m["date"],
     "probabilities":distribution,"rating_home":round(rh,1),"rating_away":round(ra,1),
     "games_home":games_played[home],"games_away":games_played[away],
     "low_sample":min(games_played[home],games_played[away])<8,
     "rating_difference_including_home_advantage":round(rh-ra+params["home_advantage"],1),
     "historical_cutoff_exclusive":day,"parameters":params,
     "formula":"x=10^((rating_home-rating_away+home_advantage)/(2*scale)); P=(x,draw_strength,1/x)/(x+draw_strength+1/x)",
     "status":"CHALLENGER_ONLY_not_a_betting_recommendation"}
  for home,away,delta in pending:
   ratings[home]=ratings.get(home,BASE)+delta;ratings[away]=ratings.get(away,BASE)-delta
   games_played[home]+=1;games_played[away]+=1
 return history,predictions


def evaluate(hist,fixtures,as_of=None,comparison=None):
 research=comparison or calibration.compare_1x2(hist,as_of=as_of)
 selected=research["selected"];winner=selected["elo_candidate"]
 rows,_=calibration.prepare_history(hist,as_of)
 now=as_of or datetime.now(timezone.utc);horizon=(now.date()+timedelta(days=30)).isoformat()
 upcoming=[f for f in fixtures if now.date().isoformat()<=f["date"]<=horizon and runner.future_match(f,now)]
 live=list(process(rows,CANDIDATES[winner],upcoming,as_of)[1].values())
 audit=research["holdout"];gain=audit["gains_vs_poisson"]["elo"]
 by_league={league:{"n":v["n"],"elo_logloss":v["models"]["elo"]["log_loss"],
   "current_logloss":v["models"]["poisson"]["log_loss"],"mean_gain":v["gains_vs_poisson"]["elo"]["mean"],
   "approx_95_ci":v["gains_vs_poisson"]["elo"]["approx_95_ci"],
   "elo_brier":v["models"]["elo"]["brier"],"current_brier":v["models"]["poisson"]["brier"],
   "elo_ece":v["models"]["elo"]["ece"],"current_ece":v["models"]["poisson"]["ece"]}
   for league,v in audit["by_league"].items()}
 return {"generated_at":research["generated_at"],"status":"RESEARCH_ONLY_NOT_PROMOTED",
   "rating_method":"Davidson three-outcome Elo; updates after all matches of same date; league-isolated ratings",
   "selection":"Global calendar validation only; separate calibration window; final period used for exploratory reporting only",
   "candidates":CANDIDATES,"best_candidate":winner,"protocol":research["protocol"],
   "validation_scores":[{"model":name,**metrics} for name,metrics in research["selection_scores"].items()],
   "holdout":{"n":audit["n"],"logloss_gain_vs_current":gain["mean_logloss_gain"],
     "approx_95_ci":gain["approx_95_ci"],"interval_method":gain["method"],"weeks":gain["blocks"],"by_league":by_league},
   "limitations":research["limitations"],"production_model_changed":False,"live_research_only":live}
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
