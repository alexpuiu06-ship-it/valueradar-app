#!/usr/bin/env python3
"""ValueRadar: experimental forecasts from public data; never bookmaker scraping."""
from __future__ import annotations
import csv, io, json, math, re, sys, unicodedata, urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
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
 now=datetime.now(timezone.utc).date().isoformat()
 seen=set(result)
 upcoming=[m for k,m in fixture.items() if m["date"]>=now and k not in seen]
 # Do not predict past events just because today's fixtures have already kicked off.
 return sorted(result.values(),key=lambda x:x["date"]),sorted(upcoming,key=lambda x:x["date"]),sorted(report,key=lambda x:(x["league"],x["kind"]))
def wmean(rows,col,date):
 sw=0.; sy=0.
 for m in rows:
  age=max(0,(date-datetime.fromisoformat(m["date"]).date()).days)
  w=2**(-age/185)
  sw+=w; sy+=w*m[col]
 return sy/max(.001,sw),sw
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
 def shrunk(rows,col,avg):
  m,n=wmean(rows,col,date)
  return (m*n+7*avg)/(n+7)
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
 return {"line":line,"over":round(p,5),"under":round(1-p,5),
  "mean":round(mu,2),"n_league":len(relevant),"n_home":len(home),
  "n_away":len(away),"small_sample":min(len(home),len(away))<8 or len(relevant)<100,
  "status":"experimental"}
def over_tail(mu,line,dispersion=1):
 k=max(.5,mu/(dispersion-1)) if dispersion>1.07 else float("inf")
 term=(k/(k+mu))**k if math.isfinite(k) else math.exp(-mu)
 s=term
 for n in range(1,int(math.floor(line))+1):
  term*= ((n-1+k)/n)*mu/(k+mu) if math.isfinite(k) else mu/n
  s+=term
 return max(0.,min(1.,1.-s))
def validation(hist,market):
 h,a,line,minimum=MARKETS[market]; preds=[]
 for lg in LEAGUES:
  rows=[r for r in hist if r["league"]==lg and r.get(h) is not None and r.get(a) is not None]
  rows.sort(key=lambda r:r["date"])
  start=max(minimum,int(len(rows)*.75))
  for i in range(start,len(rows)):
   p=pred(rows[:i],rows[i],market)
   if p is None:continue
   y=int(rows[i][h]+rows[i][a]>line)
   older=rows[max(0,i-50):i]
   baseline=(2.5+sum(int(v[h]+v[a]>line) for v in older))/(5+len(older))
   preds.append((p["over"],baseline,y))
 if len(preds)<20:return {"n":len(preds),"status":"insufficient"}
 return {"n":len(preds),"status":"experimental",
  "brier":round(sum((p-y)**2 for p,b,y in preds)/len(preds),5),
  "baseline_brier":round(sum((b-y)**2 for p,b,y in preds)/len(preds),5)}
def prospective(hist,fixtures,run_at):
 path=OUT/"forecast_log.json"
 try:
  log=json.loads(path.read_text()) if path.exists() else []
  if not isinstance(log,list):log=[]
 except Exception:log=[]
 def logkey(x):
  return (x["league"],x["date"],norm(x["home"]),norm(x["away"]),x["market"])
 known={logkey(r) for r in log}
 today=datetime.now(timezone.utc).date().isoformat()
 for f in fixtures:
  if f["date"]<=today:continue
  for market,p in f["markets"].items():
   if p is None:continue
   entry={k:f[k] for k in ("league","date","home","away")}
   entry.update({"market":market,"line":p["line"],"p_over":p["over"],"created_at":run_at,"settled":False})
   if logkey(entry) not in known: log.append(entry); known.add(logkey(entry))
 outcomes={key(r):r for r in hist}
 for r in log:
  if r.get("settled"):continue
  played=outcomes.get(tuple(logkey(r)[:4]))
  if not played:continue
  h,a,_,_=MARKETS[r["market"]]
  if played.get(h) is None or played.get(a) is None:continue
  r["actual_total"]=played[h]+played[a]
  r["actual_over"]=int(r["actual_total"]>r["line"])
  r["settled"]=True
  r["settled_at"]=run_at
 log=sorted(log,key=lambda r:(r["date"],r["league"],r["home"],r["market"]))[-3500:]
 path.write_text(json.dumps(log,ensure_ascii=False,indent=2),encoding="utf-8")
 return {market:{"n":len(ss),"brier":round(sum((r["p_over"]-r["actual_over"])**2 for r in ss)/len(ss),5) if ss else None}
  for market in MARKETS for ss in [[r for r in log if r.get("settled") and r["market"]==market]]},len(log)
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
 payload={"version":"0.6","generated_at":stamp,"history_rows":len(hist),
  "fixture_rows":len(fixtures),"source_success":sum(r["ok"] for r in report),
  "source_total":len(report),"source_report":report,"data_audit":audit,
  "backtest":{m:validation(hist,m) for m in MARKETS},
  "prospective":prospective_report,"prospective_predictions_recorded":count,
  "fixtures":enriched,"message":"EXPERIMENTAL model; no bookmaker odds feed and no validated value bets."}
 (OUT/"latest.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
 print(f"Published {len(enriched)} forecasts, {len(hist)} historical matches")
 return 0
def selftest():
 assert abs(over_tail(1.,0.5)-(1-math.exp(-1)))<1e-8
 assert norm("Arsenal FC")=="arsenal"
 assert norm("Man Utd")=="manchesterunited"
 assert number("") is None
 assert pred([],{"league":"Ligue 1","date":"2026-11-10","home":"A","away":"B"},"goals") is None
 print("Self-tests passed.")
if __name__=="__main__":
 sys.exit((selftest() or 0) if "--self-test" in sys.argv else run())
