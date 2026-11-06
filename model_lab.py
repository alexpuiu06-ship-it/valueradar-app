#!/usr/bin/env python3
"""Controlled chronological model comparison. Never self-promote a model."""
from __future__ import annotations
import json, math, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import runner

OUT=Path(__file__).resolve().parent/"docs"
VARIANTS={
 "current_v1":{"half_life_days":185,"prior_weight":7,"opponent_effect":True},
 "recent_90d":{"half_life_days":90,"prior_weight":7,"opponent_effect":True},
 "regularized_15":{"half_life_days":185,"prior_weight":15,"opponent_effect":True},
 "team_only":{"half_life_days":185,"prior_weight":7,"opponent_effect":False}
}
MARKETS=["h2h","yellow","corners","goals","fouls"]
def brier(probs,y):
 if isinstance(probs,dict):
  return sum((probs[k]-float(k==y))**2 for k in ("home","draw","away"))/3
 return (probs-y)**2
def logloss(probs,y):
 if isinstance(probs,dict):p=probs[y]
 else:p=probs if y else 1-probs
 return -math.log(max(1e-6,min(1-1e-6,p)))
def actual(match,market):
 if market=="h2h":
  return ("home" if match["gh"]>match["ga"] else
   "away" if match["gh"]<match["ga"] else "draw")
 h,a,limit,_=runner.MARKETS[market]
 return int(match[h]+match[a]>limit)
def main_probs(prediction,market):
 if market=="h2h":return prediction.get("h2h")
 return prediction.get("over")
def experiment(hist):
 output={"generated_at":datetime.now(timezone.utc).isoformat(),
  "status":"research_only_no_model_promoted",
  "model_selection":"choose by validation log-loss only; final holdout remains untouched",
  "variants":VARIANTS,"markets":{}}
 for market in MARKETS:
  h,a,limit,minimum=runner.MARKETS["goals" if market=="h2h" else market]
  val_records=defaultdict(list);test_records=defaultdict(list)
  availability={}
  for league in runner.LEAGUES:
   rows=[r for r in hist if r["league"]==league and r.get(h) is not None and r.get(a) is not None]
   rows.sort(key=lambda r:r["date"])
   n=len(rows)
   availability[league]=n
   split_val=max(minimum,int(n*.55))
   split_test=max(split_val+1,int(n*.78))
   for i in range(split_val,n):
    m=rows[i];prior=rows[:i];predictions={}
    for name,params in VARIANTS.items():
     pred=runner.pred(prior,m,"goals" if market=="h2h" else market,**params)
     predictions[name]=main_probs(pred,market) if pred else None
    if any(x is None for x in predictions.values()):continue
    y=actual(m,market)
    target=val_records if i<split_test else test_records
    for name,prob in predictions.items():target[name].append((prob,y))
  def summarize(group):
   return {name:{"n":len(points),"brier":round(sum(brier(p,y) for p,y in points)/len(points),5) if points else None,
    "log_loss":round(sum(logloss(p,y) for p,y in points)/len(points),5) if points else None}
    for name,points in group.items()}
  val=summarize(val_records)
  test=summarize(test_records)
  # We do NOT choose the winner using the holdout.
  contenders=[(metrics["log_loss"],name) for name,metrics in val.items() if metrics["n"]>=20]
  chosen=min(contenders)[1] if contenders else None
  improvement=None
  if chosen and chosen in test and test[chosen]["n"]>=20 and test.get("current_v1",{}).get("log_loss") is not None:
   improvement=round(test["current_v1"]["log_loss"]-test[chosen]["log_loss"],5)
  output["markets"][market]={
   "historical_examples":availability,"selected_on_validation":chosen,
   "validation":val,"holdout":test,
   "holdout_logloss_gain_vs_current":improvement,
   "approval":"NOT_APPROVED_no_significance_or_prospective_validation",
   "note":"Selection used validation only, and results are not betting ROI. Missing markets may have very small samples."
  }
 return output
def selftest():
 assert abs(brier(.7,1)-.09)<1e-9
 assert abs(brier({"home":1.,"draw":0.,"away":0.},"home"))<1e-9
 assert logloss(.7,1)>0
 hist=[]
 from datetime import date,timedelta
 for i in range(160):
  d=(date(2026,1,1)+timedelta(days=i)).isoformat()
  hist.append({"league":"Ligue 1","date":d,"home":"A","away":"B",
               "gh":2.,"ga":1.,"yh":2.,"ya":2.,"ch":5.,"ca":4.,"fh":14.,"fa":9.})
 x=experiment(hist)
 assert set(x["markets"])==set(MARKETS)
 assert x["markets"]["h2h"]["approval"].startswith("NOT_APPROVED")
 print("Model lab tests passed")
def run():
 OUT.mkdir(parents=True,exist_ok=True)
 hist,fixtures,report=runner.load_all()
 if len(hist)<100:
  raise SystemExit("Insufficient real history: preserve last model lab report")
 result=experiment(hist)
 (OUT/"model_lab.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf8")
 print("Evaluated:",{m:(r["selected_on_validation"],r["holdout"].get("current_v1",{}).get("n",0))
  for m,r in result["markets"].items()})
if __name__=="__main__":
 selftest() if "--self-test" in sys.argv else run()
