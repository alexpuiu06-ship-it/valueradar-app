#!/usr/bin/env python3
"""Evaluate historical odds observations against completed outcomes (paper-only)."""
from __future__ import annotations
import json, math, sys
from collections import defaultdict
from pathlib import Path
import runner

OUT=Path(__file__).resolve().parent/"docs"
def read(name,default):
 try:return json.loads((OUT/name).read_text(encoding="utf-8"))
 except (FileNotFoundError,ValueError):return default
def key(v):
 return (v["league"],v["date"],runner.norm(v["home"]),runner.norm(v["away"]))
def evaluate(observations,forecast):
 finished={key(x):x for x in forecast if x.get("market")=="h2h" and x.get("settled") and x.get("actual_outcome")}
 grouped=defaultdict(list)
 for r in observations:
  try:
   if not all(f in r for f in ("league","date","home","away","outcome","bookmaker_id","odds","observed_at")):continue
   if not 1.01<float(r["odds"])<100:continue
   grouped[key(r)].append(r)
  except (ValueError,TypeError,KeyError):continue
 selected=[];signal_count=0;all_observations=sum(len(v) for v in grouped.values())
 for event,records in grouped.items():
  records.sort(key=lambda x:x["observed_at"])
  first=records[0]["observed_at"]
  # First-scanned quotes only. Never retrospectively select the highest price
  # across all snapshots. Multiple quotes in one scan are comparable.
  first_batch=[r for r in records if r["observed_at"]==first]
  qualified=[r for r in first_batch if r.get("estimated_ev",0)>=.05 and not r.get("model_low_sample",True)]
  if not qualified:continue
  choice=max(qualified,key=lambda x:(x["estimated_ev"],x["odds"]))
  signal_count+=1
  settled=finished.get(event)
  if not settled:continue
  payoff=(choice["odds"]-1) if settled["actual_outcome"]==choice["outcome"] else -1
  # Last observed price at the same bookmaker before settlement; not a guaranteed closing line.
  same=[x for x in records if x.get("bookmaker_id")==choice["bookmaker_id"] and x["outcome"]==choice["outcome"]]
  later=same[-1] if same else choice
  selected.append({"event":event,"outcome":choice["outcome"],"bookmaker_id":choice["bookmaker_id"],
    "price":choice["odds"],"model_probability":choice["model_probability"],
    "estimated_ev":choice["estimated_ev"],"payoff":payoff,
    "last_seen_price":later["odds"],"price_change":round(choice["odds"]/later["odds"]-1,5),
    "has_multiple_prices":len(same)>1})
 values=[s["payoff"] for s in selected]
 roi=sum(values)/len(values) if values else None
 stderr=None;bounds=None
 if len(values)>2:
  avg=roi
  sd=math.sqrt(sum((v-avg)**2 for v in values)/(len(values)-1))
  stderr=sd/math.sqrt(len(values))
  bounds=[round(avg-1.96*stderr,5),round(avg+1.96*stderr,5)]
 changes=[s["price_change"] for s in selected if s["has_multiple_prices"]]
 return {"status":"paper_only_not_validated","observations":all_observations,
  "distinct_events":len(grouped),"initial_positive_ev_signals":signal_count,
  "signals_settled":len(selected),"hypothetical_roi":round(roi,5) if roi is not None else None,
  "approx_95_roi_interval":bounds,
  "mean_price_change_vs_last_seen":round(sum(changes)/len(changes),5) if changes else None,
  "price_change_count":len(changes),"model_is_verified":False,
  "quotes_are_verified_romania":False,
  "notice":"Paper results are not executable bets, the bookmaker may not be accessible in Romania, and these are not verified closing-line prices."}
def selftest():
 event={"league":"Premier League","date":"2026-11-07","home":"Arsenal","away":"Chelsea"}
 x={**event,"outcome":"home","bookmaker_id":"test","odds":2.1,
    "estimated_ev":.08,"model_probability":.51,"model_low_sample":False,
    "observed_at":"2026-11-06T15:00:00Z"}
 completed={**event,"market":"h2h","settled":True,"actual_outcome":"home"}
 a=evaluate([x],[completed])
 assert a["signals_settled"]==1 and abs(a["hypothetical_roi"]-1.1)<.00001
 x["model_low_sample"]=True
 assert evaluate([x],[completed])["signals_settled"]==0
 print("Paper-tracking tests passed")
def run():
 OUT.mkdir(parents=True,exist_ok=True)
 d=evaluate(read("odds_observations.json",[]),read("forecast_log.json",[]))
 (OUT/"market_audit.json").write_text(json.dumps(d,indent=2,ensure_ascii=False),encoding="utf8")
 print("Market audit:",d["observations"],"observations,",d["signals_settled"],"settled paper signals")
if __name__=="__main__":
 (selftest() if "--self-test" in sys.argv else run())
