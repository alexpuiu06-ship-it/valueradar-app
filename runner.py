#!/usr/bin/env python3
"""ValueRadar: experimental forecasts from public data; never bookmaker scraping."""
from __future__ import annotations
import csv, io, json, math, re, sys, unicodedata, urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

BASE=Path(__file__).resolve().parent
OUT=BASE/"docs"
OM="https://raw.githubusercontent.com/oladeeayo/open-matchday/master/data"
OF="https://raw.githubusercontent.com/openfootball/football.json/master"
LEAGUES={
 "Premier League":("ENG_1_premier-league","en.1"),
 "La Liga":("ESP_1_la-liga","es.1"),
 "Serie A":("ITA_1_serie-a","it.1"),
 "Bundesliga":("GER_1_bundesliga","de.1"),
 "Ligue 1":("FRA_1_ligue-1","fr.1")}
MARKETS={"yellow":("yh","ya",4.5,35),"corners":("ch","ca",9.5,35),
         "goals":("gh","ga",2.5,70),"fouls":("fh","fa",23.5,35)}
ALIASES={"manutd":"manchesterunited","mancity":"manchestercity",
 "spurs":"tottenhamhotspur","nottmforest":"nottinghamforest",
 "wolves":"wolverhamptonwanderers","inter":"internazionale",
 "psg":"parissaintgermain"}
def norm(x):
 x=unicodedata.normalize("NFD",str(x).lower())
 x="".join(c for c in x if unicodedata.category(c)!="Mn")
 x=re.sub(r"\b(fc|afc|cf|sc|club|football|calcio)\b","",x)
 x=re.sub("[^a-z0-9]","",x)
 return ALIASES.get(x,x)
def number(x):
 try:
  n=float(x)
  return n if math.isfinite(n) and n>=0 else None
 except (ValueError,TypeError): return None
def key(m):
 return (m["league"],m["date"],norm(m["home"]),norm(m["away"]))
def get_text(url):
 request=urllib.request.Request(url,headers={"User-Agent":"ValueRadar-research/0.6"})
 with urllib.request.urlopen(request,timeout=11) as res:
  return res.read(1800000).decode("utf-8-sig")
def tasks():
 for league,(slug,short) in LEAGUES.items():
  yield league,"results",f"{OM}/{slug}/results_2627.csv"
  yield league,"fixtures",f"{OM}/{slug}/fixtures_2627.csv"
  for season in ("2024-25","2025-26"):
   yield league,"historical",f"{OF}/{season}/{short}.json"
def fixture_kickoff(m):
 """Upstream fixture times are documented as fixed UTC+01:00."""
 try:
  value=str(m.get("time",""))
  if not re.fullmatch(r"\d{2}:\d{2}",value): return None
  naive=datetime.strptime(m["date"]+"T"+value,"%Y-%m-%dT%H:%M")
  return naive.replace(tzinfo=timezone(timedelta(hours=1)))
 except (ValueError,TypeError,KeyError): return None
def future_match(m,at):
 kickoff=fixture_kickoff(m)
 return kickoff.astimezone(timezone.utc)>at if kickoff else m["date"]>at.date().isoformat()
def local_kickoff(m):
 kickoff=fixture_kickoff(m)
 return kickoff.astimezone(ZoneInfo("Europe/Bucharest")).strftime("%H:%M") if kickoff else None
def load_all():
 result,fixture,report={}, {}, []
 jobs=list(tasks())
 with ThreadPoolExecutor(max_workers=6) as pool:
  pending={pool.submit(get_text,url):(league,kind,url) for league,kind,url in jobs}
  for future in as_completed(pending):
   league,kind,url=pending[future]
   try:
    content=future.result()
    rows=list(csv.DictReader(io.StringIO(content))) if url.endswith(".csv") else json.loads(content).get("matches",[])
    for r in rows:
     if kind=="historical":
      date=r.get("date"); home=r.get("team1"); away=r.get("team2")
      score=r.get("score")
      if isinstance(score,dict): score=score.get("ft")
      if not isinstance(score,list) or len(score)!=2: continue
      values={"gh":number(score[0]),"ga":number(score[1])}
     else:
      date=r.get("date"); home=r.get("home"); away=r.get("away")
      values={"gh":number(r.get("ft_home")),"ga":number(r.get("ft_away")),
       "yh":number(r.get("home_yellow")),"ya":number(r.get("away_yellow")),
       "ch":number(r.get("home_corners")),"ca":number(r.get("away_corners")),
       "fh":number(r.get("home_fouls")),"fa":number(r.get("away_fouls"))}
     try: datetime.strptime(str(date),"%Y-%m-%d")
     except ValueError: continue
     if not home or not away: continue
     m={"league":league,"date":date,"home":home,"away":away}
     k=key(m)
     if kind=="fixtures":
      fixture[k]={**m,"time":r.get("time","")}
     elif values.get("gh") is not None and values.get("ga") is not None:
      old=result.get(k)
      # Preserve recent stats when multiple sources cover the same match.
      if old:
       for field,v in values.items():
        if v is not None and old.get(field) is None: old[field]=v
      else:
       result[k]={**m,**{f:v for f,v in values.items() if v is not None}}
    report.append({"league":league,"kind":kind,"ok":True,"rows":len(rows)})
   except Exception as exc:
    report.append({"league":league,"kind":kind,"ok":False,"error":str(exc)[:120]})
 now=datetime.now(timezone.utc)
 seen=set(result)
 upcoming=[{**m,"time_ro":local_kickoff(m)} for k,m in fixture.items() if future_match(m,now) and k not in seen]
 # Exclude matches already kicked off (including today's).
 return sorted(result.values(),key=lambda x:x["date"]),sorted(upcoming,key=lambda x:x["date"]),sorted(report,key=lambda x:(x["league"],x["kind"]))
def wmean(rows,col,date):
 sw=0.; sy=0.
 for m in rows:
  age=max(0,(date-datetime.fromisoformat(m["date"]).date()).days)
  w=2**(-age/185)
  sw+=w; sy+=w*m[col]
 return sy/max(.001,sw),sw
def h2h_distribution(lamh,lama):
 """Independent Poisson 1X2 distribution, normalized (finite truncation)."""
 if lamh is None or lama is None:return None
 def mass(lam):
  out=[math.exp(-lam)]
  for k in range(1,25):out.append(out[-1]*lam/k)
  return out
 h,a=mass(lamh),mass(lama)
 ph=pd=pa=0.
 for i,hi in enumerate(h):
  for j,aj in enumerate(a):
   if i>j:ph+=hi*aj
   elif i==j:pd+=hi*aj
   else:pa+=hi*aj
 z=ph+pd+pa
 if z<=0:return None
 return {"home":round(ph/z,5),"draw":round(pd/z,5),"away":round(pa/z,5)}

def pred(hist,match,market):
 homecol,awaycol,line,minimum=MARKETS[market]
 relevant=[m for m in hist if m["league"]==match["league"] and m["date"]<match["date"]
  and m.get(homecol) is not None and m.get(awaycol) is not None]
 if len(relevant)<minimum: return None
 homeid,awayid=norm(match["home"]),norm(match["away"])
 home=[r for r in relevant if norm(r["home"])==homeid]
 away=[r for r in relevant if norm(r["away"])==awayid]
 if min(len(home),len(away))<3: return None
 date=datetime.fromisoformat(match["date"]).date()
 baseh,_=wmean(relevant,homecol,date); basea,_=wmean(relevant,awaycol,date)
 if baseh<=0 or basea<=0: return None
 PRIOR_WEIGHT=7
 HALF_LIFE_DAYS=185
 def shrunk(rows,col,avg):
  m,n=wmean(rows,col,date)
  return (m*n+PRIOR_WEIGHT*avg)/(n+PRIOR_WEIGHT)
 home_attack_raw,home_effective=wmean(home,homecol,date)
 opposing_home_conceded_raw,opposing_effective=wmean(away,homecol,date)
 away_attack_raw,away_effective=wmean(away,awaycol,date)
 opposing_away_conceded_raw,opposing_away_effective=wmean(home,awaycol,date)
 h_attack=shrunk(home,homecol,baseh)
 h_conceded=shrunk(away,homecol,baseh)
 a_attack=shrunk(away,awaycol,basea)
 a_conceded=shrunk(home,awaycol,basea)
 lamh=max(.05,min(baseh*2.4,math.sqrt(h_attack*h_conceded)))
 lama=max(.05,min(basea*2.4,math.sqrt(a_attack*a_conceded)))
 mu=lamh+lama
 totals=[r[homecol]+r[awaycol] for r in relevant]
 avg=sum(totals)/len(totals)
 variance=sum((v-avg)**2 for v in totals)/max(1,len(totals)-1)
 dispersion=max(1.,min(2.5,variance/max(.1,avg)))
 p=over_tail(mu,line,dispersion)
 explanation={
   "method_version":"weighted_opponent_model_v1",
   "status":"arithmetic_trace_not_causal_explanation",
   "source_families":["OpenFootball football.json (historic goals)",
                      "open-matchday (current season and event summaries)"],
   "historical_cutoff_exclusive":match["date"],
   "half_life_days":HALF_LIFE_DAYS,"prior_pseudogames":PRIOR_WEIGHT,
   "league_home_mean":round(baseh,4),"league_away_mean":round(basea,4),
   "home_team_for_mean_raw":round(home_attack_raw,4),
   "away_opponent_concedes_to_home_raw":round(opposing_home_conceded_raw,4),
   "away_team_for_mean_raw":round(away_attack_raw,4),
   "home_opponent_concedes_to_away_raw":round(opposing_away_conceded_raw,4),
   "home_team_effective_matches":round(home_effective,2),
   "away_team_effective_matches":round(away_effective,2),
   "away_opponent_effective_matches":round(opposing_effective,2),
   "home_opponent_effective_matches":round(opposing_away_effective,2),
   "home_attack_shrunk":round(h_attack,4),
   "opponent_home_conceded_shrunk":round(h_conceded,4),
   "away_attack_shrunk":round(a_attack,4),
   "opponent_away_conceded_shrunk":round(a_conceded,4),
   "league_total_mean":round(baseh+basea,4),
   "predicted_home_mean":round(lamh,4),
   "predicted_away_mean":round(lama,4),
   "predicted_total_mean":round(mu,4),
   "home_shift_vs_league":round(lamh-baseh,4),
   "away_shift_vs_league":round(lama-basea,4),
   "dispersion":round(dispersion,4),
   "count_distribution":"negative_binomial" if dispersion>1.07 else "poisson",
   "missing_factors":["referee","confirmed_lineups","injuries","tactical_matchup",
                     "independent_odds_validation"],
   "warning":"Efectele sunt caracteristici ale formulei, nu cauze dovedite."
 }
 return {"line":line,"over":round(p,5),"under":round(1-p,5),
  "mean":round(mu,2),"n_league":len(relevant),"n_home":len(home),
  "n_away":len(away),"small_sample":min(len(home),len(away))<8 or len(relevant)<100,
  "status":"experimental",
  "quality":"very_low" if min(len(home),len(away))<8 or len(relevant)<150 else "unverified",
  "h2h":h2h_distribution(lamh,lama) if market=="goals" else None,
  "explanation":explanation}
def over_tail(mu,line,dispersion=1):
 k=max(.5,mu/(dispersion-1)) if dispersion>1.07 else float("inf")
 term=(k/(k+mu))**k if math.isfinite(k) else math.exp(-mu)
 s=term
 for n in range(1,int(math.floor(line))+1):
  term*= ((n-1+k)/n)*mu/(k+mu) if math.isfinite(k) else mu/n
  s+=term
 return max(0.,min(1.,1.-s))
def validation(hist,market):
 h,a,line,minimum=MARKETS[market]
 preds=[]; per_league={}
 for lg in LEAGUES:
  rows=[r for r in hist if r["league"]==lg and r.get(h) is not None and r.get(a) is not None]
  rows.sort(key=lambda r:r["date"])
  start=max(minimum,int(len(rows)*.75))
  for_league=[]
  for i in range(start,len(rows)):
   p=pred(rows[:i],rows[i],market)
   if p is None:continue
   y=int(rows[i][h]+rows[i][a]>line)
   older=[r for r in rows[max(0,i-50):i] if r["date"]<rows[i]["date"]]
   baseline=(2.5+sum(int(v[h]+v[a]>line) for v in older))/(5+len(older))
   for_league.append((p["over"],baseline,y))
  per_league[lg]=len(for_league)
  preds.extend(for_league)
 if len(preds)<20:return {"n":len(preds),"status":"insufficient","per_league":per_league}
 def brier(p,y):return (p-y)**2
 def logloss(p,y):
  p=max(.00001,min(.99999,p))
  return -(y*math.log(p)+(1-y)*math.log(1-p))
 d=[brier(b,y)-brier(p,y) for p,b,y in preds]
 improvement=sum(d)/len(d)
 sd=(sum((x-improvement)**2 for x in d)/max(1,len(d)-1))**.5
 err=1.96*sd/(len(d)**.5)
 bins=[]
 for lower in range(0,10,2):
  bucket=[(p,y) for p,b,y in preds if lower/10<=p<min(1.,(lower+2)/10+1e-8)]
  if bucket:
   bins.append({"range":f"{lower*10}-{(lower+2)*10}%",
    "n":len(bucket),"predicted":round(sum(p for p,y in bucket)/len(bucket),4),
    "observed":round(sum(y for p,y in bucket)/len(bucket),4)})
 ece=sum(x["n"]*abs(x["predicted"]-x["observed"]) for x in bins)/len(preds)
 return {"n":len(preds),"status":"preliminary" if len(preds)<300 else "experimental",
  "brier":round(sum(brier(p,y) for p,b,y in preds)/len(preds),5),
  "baseline_brier":round(sum(brier(b,y) for p,b,y in preds)/len(preds),5),
  "log_loss":round(sum(logloss(p,y) for p,b,y in preds)/len(preds),5),
  "baseline_log_loss":round(sum(logloss(b,y) for p,b,y in preds)/len(preds),5),
  "brier_improvement":round(improvement,5),
  "improvement_approx_95_range":[round(improvement-err,5),round(improvement+err,5)],
  "ece":round(ece,4),"bins":bins,"per_league":per_league}
def validation_h2h(hist):
 rows_by={lg:sorted([r for r in hist if r["league"]==lg and r.get("gh") is not None and r.get("ga") is not None],key=lambda r:r["date"]) for lg in LEAGUES}
 test=[]; league_counts={}
 for lg,rows in rows_by.items():
  start=max(70,int(len(rows)*.75)); results=[]
  for i in range(start,len(rows)):
   p=pred(rows[:i],rows[i],"goals")
   if not p or not p.get("h2h"):continue
   probs=p["h2h"]; outcome="home" if rows[i]["gh"]>rows[i]["ga"] else "away" if rows[i]["gh"]<rows[i]["ga"] else "draw"
   older=[r for r in rows[max(0,i-80):i] if r["date"]<rows[i]["date"]]
   counts={"home":3,"draw":3,"away":3}
   for r in older:
    o="home" if r["gh"]>r["ga"] else "away" if r["gh"]<r["ga"] else "draw"
    counts[o]+=1
   denom=sum(counts.values())
   baseline={k:v/denom for k,v in counts.items()}
   results.append((probs,baseline,outcome))
  league_counts[lg]=len(results);test.extend(results)
 def brier(p,y):return sum((p[k]-(1 if k==y else 0))**2 for k in ("home","draw","away"))/3
 def logloss(p,y):return -math.log(max(.00001,p[y]))
 if len(test)<20:return {"n":len(test),"status":"insufficient","per_league":league_counts}
 d=[brier(base,y)-brier(p,y) for p,base,y in test]
 avg=sum(d)/len(d);sd=(sum((v-avg)**2 for v in d)/max(1,len(d)-1))**.5
 return {"n":len(test),"status":"unverified", "brier":round(sum(brier(p,y) for p,base,y in test)/len(test),5),
 "baseline_brier":round(sum(brier(base,y) for p,base,y in test)/len(test),5),
 "log_loss":round(sum(logloss(p,y) for p,base,y in test)/len(test),5),
 "baseline_log_loss":round(sum(logloss(base,y) for p,base,y in test)/len(test),5),
 "improvement_approx_95_range":[round(avg-1.96*sd/math.sqrt(len(d)),5),round(avg+1.96*sd/math.sqrt(len(d)),5)],
 "per_league":league_counts}

def prospective(hist,fixtures,run_at):
 """Write once, settle later; never rewrite the original forecast."""
 path=OUT/"forecast_log.json"
 try:
  log=json.loads(path.read_text()) if path.exists() else []
  if not isinstance(log,list):log=[]
 except Exception:log=[]
 def logkey(x):
  return (x["league"],x["date"],norm(x["home"]),norm(x["away"]),x["market"])
 known={logkey(r) for r in log}
 now=datetime.now(timezone.utc)
 for f in fixtures:
  if not future_match(f,now):continue
  for market,p in f["markets"].items():
   if p is None:continue
   entry={k:f[k] for k in ("league","date","home","away")}
   entry.update({"market":market,"line":p["line"],"p_over":p["over"],"created_at":run_at,"settled":False})
   if logkey(entry) not in known: log.append(entry);known.add(logkey(entry))
  gp=f["markets"].get("goals")
  if gp and gp.get("h2h"):
   entry={k:f[k] for k in ("league","date","home","away")}
   entry.update({"market":"h2h","probabilities":gp["h2h"],"created_at":run_at,"settled":False})
   if logkey(entry) not in known:log.append(entry);known.add(logkey(entry))
 outcomes={key(r):r for r in hist}
 for r in log:
  if r.get("settled"):continue
  played=outcomes.get(tuple(logkey(r)[:4]))
  if not played:continue
  if r["market"]=="h2h":
   if played.get("gh") is None or played.get("ga") is None:continue
   y="home" if played["gh"]>played["ga"] else "away" if played["gh"]<played["ga"] else "draw"
   r["actual_outcome"]=y
  else:
   h,a,_,_=MARKETS.get(r["market"],(None,None,None,None))
   if h is None or played.get(h) is None or played.get(a) is None:continue
   r["actual_total"]=played[h]+played[a]
   r["actual_over"]=int(r["actual_total"]>r["line"])
  r["settled"]=True
  r["settled_at"]=run_at
 log=sorted(log,key=lambda r:(r["date"],r["league"],r["home"],r["market"]))[-5000:]
 path.write_text(json.dumps(log,ensure_ascii=False,indent=2),encoding="utf-8")
 scores={}
 for market in list(MARKETS)+["h2h"]:
  done=[r for r in log if r.get("settled") and r["market"]==market]
  if market=="h2h":
   def error(r):
    return sum((r["probabilities"][k]-(1 if r["actual_outcome"]==k else 0))**2 for k in ("home","draw","away"))/3
  else:
   def error(r):
    return (r["p_over"]-r["actual_over"])**2
  scores[market]={"n":len(done),"brier":round(sum(error(r) for r in done)/len(done),5) if done else None}
 return scores,len(log)
def run():
 OUT.mkdir(parents=True,exist_ok=True)
 hist,fixtures,report=load_all()
 if len(hist)<100 or not fixtures:
  print("Insufficient data; preserving existing dashboard.",file=sys.stderr)
  return 2
 today=datetime.now(timezone.utc).date()
 upcoming=[m for m in fixtures if m["date"] <= (today+timedelta(days=30)).isoformat()]
 enriched=[{**m,"markets":{k:pred(hist,m,k) for k in MARKETS}} for m in upcoming]
 stamp=datetime.now(timezone.utc).isoformat()
 prospective_report,count=prospective(hist,enriched,stamp)
 audit={lg:{market:sum(r["league"]==lg and r.get(h) is not None and r.get(a) is not None for r in hist)
  for market,(h,a,_,_) in MARKETS.items()} for lg in LEAGUES}
 freshness={lg:{market:max((r["date"] for r in hist if r["league"]==lg and r.get(h) is not None and r.get(a) is not None),default=None)
  for market,(h,a,_,_) in MARKETS.items()} for lg in LEAGUES}
 payload={"version":"0.9","generated_at":stamp,
  "methodology":{"version":"weighted_opponent_model_v1",
   "approach":"Time-decayed team and opponent rates, shrunk toward league means, with geometric combination.",
   "prior_pseudogames":7,"half_life_days":185,
   "limitations":"No referees, lineup, tactical events, or validated ROI.",
   "details":"See ANALYSIS_METHODOLOGY.md"},"history_rows":len(hist),
  "fixture_rows":len(fixtures),"source_success":sum(r["ok"] for r in report),
  "source_total":len(report),"source_report":report,"data_audit":audit,
  "last_stat_date":freshness,
  "backtest":{**{m:validation(hist,m) for m in MARKETS},"h2h":validation_h2h(hist)},
  "prospective":prospective_report,"prospective_predictions_recorded":count,
  "fixtures":enriched,"message":"EXPERIMENTAL model; no bookmaker odds feed and no validated value bets."}
 (OUT/"latest.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
 print(f"Published {len(enriched)} forecasts, {len(hist)} historical matches")
 return 0
def selftest():
 assert abs(over_tail(1.,0.5)-(1-math.exp(-1)))<1e-8
 assert norm("Arsenal FC")=="arsenal"
 assert norm("Man Utd")=="manchesterunited"
 assert abs(sum(h2h_distribution(1.3,1.1).values())-1)<0.0001
 assert h2h_distribution(2.5,.6)["home"] > h2h_distribution(.6,2.5)["home"]
 assert number("") is None
 assert local_kickoff({"date":"2026-11-06","time":"21:00"})=="22:00"
 assert not future_match({"date":"2026-11-05","time":"23:59"},datetime(2026,11,6,18,tzinfo=timezone.utc))
 assert pred([],{"league":"Ligue 1","date":"2026-11-10","home":"A","away":"B"},"goals") is None
 # Explainability values are direct model intermediates and reconstruct the mean.
 demo=[]
 from datetime import date as date_cls
 for i in range(120):
  day=(date_cls(2026,1,1)+timedelta(days=i)).isoformat()
  demo.append({"league":"Ligue 1","date":day,"home":"A","away":"B",
               "gh":2.,"ga":1.})
 check=pred(demo,{"league":"Ligue 1","date":"2026-07-01","home":"A","away":"B"},"goals")
 assert check is not None
 explanation=check["explanation"]
 assert abs(explanation["predicted_home_mean"]+explanation["predicted_away_mean"]-
   explanation["predicted_total_mean"])<.0002
 assert explanation["historical_cutoff_exclusive"]=="2026-07-01"
 print("Self-tests passed.")
if __name__=="__main__":
 sys.exit((selftest() or 0) if "--self-test" in sys.argv else run())
