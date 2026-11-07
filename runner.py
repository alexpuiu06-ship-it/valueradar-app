#!/usr/bin/env python3
"""ValueRadar: experimental forecasts from public data; never bookmaker scraping."""
from __future__ import annotations
import csv, hashlib, io, json, math, re, sys, tempfile, unicodedata, urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

BASE=Path(__file__).resolve().parent
OUT=BASE/"docs"
PIPELINE_VERSION="validated_identity_v2"
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
# Explicit identities observed in the two source families. No fuzzy club matching.
ALIASES={"manutd":"manchesterunited","mancity":"manchestercity",
 "spurs":"tottenhamhotspur","tottenham":"tottenhamhotspur",
 "nottmforest":"nottinghamforest","wolves":"wolverhamptonwanderers",
 "wolverhampton":"wolverhamptonwanderers","inter":"internazionale",
 "internazionalemilano":"internazionale","intermilan":"internazionale",
 "psg":"parissaintgermain","parissg":"parissaintgermain",
 "brightonhovealbion":"brighton","brightonandhovealbion":"brighton",
 "ipswichtown":"ipswich","leedsunited":"leeds","newcastleunited":"newcastle",
 "westham":"westhamunited","leicester":"leicestercity",
 "athletic":"athleticbilbao","athleticclub":"athleticbilbao",
 "atleticodemadrid":"atleticomadrid","caosasuna":"osasuna",
 "cdleganes":"leganes","rcceltadevigo":"celta","celtavigo":"celta",
 "deportivoalaves":"alaves","levanteud":"levante",
 "rayovallecanodemadrid":"rayovallecano","rcdeportivo":"deportivolacoruna",
 "rcdespanyoldebarcelona":"espanyol","rcdmallorca":"mallorca",
 "realbetisbalompie":"realbetis","realsociedaddefutbol":"realsociedad",
 "rracing":"racingdesantander","udlaspalmas":"laspalmas",
 "acffiorentina":"fiorentina","acmilan":"milan","acmonza":"monza",
 "acpisa1909":"pisa","asroma":"roma","atalantabc":"atalanta",
 "bologna1909":"bologna","como1907":"como","genoacfc":"genoa",
 "parma1913":"parma","sscnapoli":"napoli","sslazio":"lazio",
 "uscremonese":"cremonese","uslecce":"lecce","ussassuolo":"sassuolo",
 "bayernmunich":"bayernmunchen","tsg1899hoffenheim":"tsghoffenheim",
 "borussiamgladbach":"borussiamonchengladbach","monchengladbach":"borussiamonchengladbach",
 "ajauxerre":"auxerre","angers":"angerssco","monaco":"asmonaco",
 "saintetienne":"assaintetienne","stetienne":"assaintetienne",
 "troyes":"estactroyes","havreathletic":"lehavreac","lehavre":"lehavreac",
 "lille":"losclille","lilleosc":"losclille","nice":"ogcnice",
 "olympiquemarseille":"olympiquedemarseille","marseille":"olympiquedemarseille",
 "lyon":"olympiquelyonnais","racingdelens":"rclens","lens":"rclens",
 "strasbourg":"rcstrasbourgalsace","stadebrestois":"stadebrestois29",
 "brest":"stadebrestois29","reims":"stadedereims","rennes":"staderennais",
 "staderennais1901":"staderennais"}
def norm(x):
 x=unicodedata.normalize("NFD",str(x).lower())
 x="".join(c for c in x if unicodedata.category(c)!="Mn")
 x=re.sub(r"\b(fc|afc|cf|sc|club|football|calcio)\b","",x)
 x=re.sub("[^a-z0-9]","",x)
 return ALIASES.get(x,x)
def number(x):
 # These fields are counts: fractions, booleans, NaN and infinity are not data.
 if isinstance(x,bool):return None
 try:
  n=float(x)
  return n if math.isfinite(n) and n>=0 and n.is_integer() else None
 except (ValueError,TypeError): return None
def key(m):
 return (m["league"],m["date"],norm(m["home"]),norm(m["away"]))
def get_text(url):
 request=urllib.request.Request(url,headers={"User-Agent":"ValueRadar-research/1.0"})
 with urllib.request.urlopen(request,timeout=11) as res:
  content=res.read(1800001)
  if len(content)>1800000:raise ValueError("Source exceeds size limit")
  return content.decode("utf-8-sig")
def tasks(at=None):
 at=at or datetime.now(timezone.utc)
 year=at.year if at.month>=7 else at.year-1
 code=f"{year%100:02d}{(year+1)%100:02d}"
 for league,(slug,short) in LEAGUES.items():
  yield league,"results",f"{OM}/{slug}/results_{code}.csv"
  yield league,"fixtures",f"{OM}/{slug}/fixtures_{code}.csv"
  for start in (year-2,year-1):
   yield league,"historical",f"{OF}/{start}-{(start+1)%100:02d}/{short}.json"
def timestamp(value):
 try:
  d=datetime.fromisoformat(str(value).replace("Z","+00:00"))
  return d.astimezone(timezone.utc) if d.tzinfo else None
 except (ValueError,TypeError):return None
def fixture_kickoff(m):
 """Fixed UTC+01:00 per open-matchday DATA_DICTIONARY.md, not Europe/Paris DST."""
 if m.get("kickoff_utc"):
  return timestamp(m["kickoff_utc"])
 try:
  value=str(m.get("time",""))
  if not re.fullmatch(r"\d{2}:\d{2}",value): return None
  naive=datetime.strptime(m["date"]+"T"+value,"%Y-%m-%dT%H:%M")
  return naive.replace(tzinfo=timezone(timedelta(hours=1)))
 except (ValueError,TypeError,KeyError): return None
def future_match(m,at):
 kickoff=fixture_kickoff(m)
 try:
  # Unknown same-day time is never treated as an upcoming pre-match offer.
  return kickoff.astimezone(timezone.utc)>at if kickoff else m["date"]>at.date().isoformat()
 except (ValueError,TypeError,KeyError):return False
def local_kickoff(m):
 kickoff=fixture_kickoff(m)
 return kickoff.astimezone(ZoneInfo("Europe/Bucharest")).strftime("%H:%M") if kickoff else None
def local_fixture(m):
 kickoff=fixture_kickoff(m)
 return {**m,"time_ro":local_kickoff(m),
   "date_ro":kickoff.astimezone(ZoneInfo("Europe/Bucharest")).date().isoformat() if kickoff else None,
   "kickoff_utc":kickoff.astimezone(timezone.utc).isoformat() if kickoff else None,
   "time_convention":"open-matchday_fixed_UTC+01:00"}
def clean_history(rows,at=None):
 """Deterministic deduplication. Conflicting observations are quarantined in full."""
 at=at or datetime.now(timezone.utc)
 accepted={};conflicts=set();rejected=defaultdict(int);duplicates=0
 counts={c for h,a,_,_ in MARKETS.values() for c in (h,a)}
 for row in rows:
  try:
   date=str(row["date"])
   if datetime.strptime(date,"%Y-%m-%d").date().isoformat()!=date:raise ValueError
   k=key(row)
   if row["league"] not in LEAGUES or not isinstance(row["home"],str) or not isinstance(row["away"],str) or not k[2] or not k[3] or k[2]==k[3]:raise ValueError
  except (ValueError,TypeError,KeyError):
   rejected["invalid_identity_or_date"]+=1;continue
  if date>at.date().isoformat():
   rejected["future_result"]+=1;continue
  if any(row.get(c) is not None and number(row[c]) is None for c in counts):
   rejected["invalid_count"]+=1;continue
  if row.get("gh") is None or row.get("ga") is None:
   rejected["missing_full_time_score"]+=1;continue
  if date==at.date().isoformat():
   kickoff=fixture_kickoff(row)
   if not kickoff or kickoff+timedelta(hours=2)>at:
    rejected["result_not_provably_completed"]+=1;continue
  row={**row,**{c:number(row[c]) for c in counts if row.get(c) is not None}}
  if k in conflicts:
   rejected["conflicting_duplicate"]+=1;continue
  if k in accepted:
   old=accepted[k]
   if any(old.get(c) is not None and row.get(c) is not None and old[c]!=row[c] for c in counts) or (fixture_kickoff(old) and fixture_kickoff(row) and fixture_kickoff(old)!=fixture_kickoff(row)):
    del accepted[k];conflicts.add(k);rejected["conflicting_duplicate"]+=2;continue
   duplicates+=1
   for c in counts:
    if old.get(c) is None and row.get(c) is not None:old[c]=row[c]
   old["source_ids"]=sorted(set(old.get("source_ids",[])+row.get("source_ids",[])))
  else:
   accepted[k]=dict(row)
 return sorted(accepted.values(),key=lambda m:key(m)),{
  "accepted":len(accepted),"duplicates_merged":duplicates,
  "conflicting_events_quarantined":len(conflicts),"conflicting_event_keys":[list(k) for k in sorted(conflicts)],"rejected":dict(sorted(rejected.items()))}
def source_season(url):
 match=re.search(r"/(20\d{2})-\d{2}/",url)
 if match:return int(match.group(1))
 match=re.search(r"_(\d{2})\d{2}\.csv$",url)
 return 2000+int(match.group(1)) if match else None
def load_all(at=None):
 now=at or datetime.now(timezone.utc)
 raw_results=[];fixture={};report=[];downloaded={}
 jobs=list(tasks(now))
 with ThreadPoolExecutor(max_workers=6) as pool:
  pending={pool.submit(get_text,url):(league,kind,url) for league,kind,url in jobs}
  for future in as_completed(pending):
   job=pending[future]
   try:downloaded[job]=(future.result(),None)
   except Exception as exc:downloaded[job]=(None,type(exc).__name__)
 # Process sources in declared order, independent of download completion order.
 for league,kind,url in jobs:
  content,error=downloaded[(league,kind,url)]
  if error:
   report.append({"league":league,"kind":kind,"ok":False,"source_url":url,"error":error});continue
  season_start=source_season(url);rejects=defaultdict(int);accepted=0
  family="OpenFootball football.json" if kind=="historical" else "open-matchday"
  source_id=f"{family}:{season_start}-{(season_start+1)%100:02d}"
  try:
   if url.endswith(".csv"):
    reader=csv.DictReader(io.StringIO(content))
    required={"date","home","away"}|({"ft_home","ft_away"} if kind=="results" else {"time"})
    if not required.issubset(reader.fieldnames or []):raise ValueError("Invalid source schema")
    rows=list(reader)
   else:
    payload=json.loads(content)
    rows=payload.get("matches")
    if not isinstance(rows,list):raise ValueError("Invalid source schema")
   for r in rows:
    if not isinstance(r,dict):rejects["invalid_row"]+=1;continue
    if kind=="historical":
     date=r.get("date");home=r.get("team1");away=r.get("team2")
     score=r.get("score")
     if isinstance(score,dict):score=score.get("ft")
     if not isinstance(score,list) or len(score)!=2:rejects["missing_full_time_score"]+=1;continue
     values={"gh":number(score[0]),"ga":number(score[1])}
    else:
     date=r.get("date");home=r.get("home");away=r.get("away")
     fields={"gh":"ft_home","ga":"ft_away","yh":"home_yellow","ya":"away_yellow",
       "ch":"home_corners","ca":"away_corners","fh":"home_fouls","fa":"away_fouls"}
     values={field:number(r.get(column)) for field,column in fields.items()}
     if any(r.get(column) not in (None,"") and number(r[column]) is None for column in fields.values()):
      rejects["invalid_count"]+=1;continue
    try:
     day=datetime.strptime(str(date),"%Y-%m-%d").date()
     if day.isoformat()!=date:raise ValueError
    except (ValueError,TypeError):rejects["invalid_date"]+=1;continue
    if not f"{season_start}-07-01"<=date<f"{season_start+1}-07-01":rejects["wrong_season"]+=1;continue
    if not isinstance(home,str) or not isinstance(away,str) or not norm(home) or not norm(away) or norm(home)==norm(away):
     rejects["invalid_identity"]+=1;continue
    m={"league":league,"date":date,"home":home,"away":away,"season":f"{season_start}-{(season_start+1)%100:02d}","source_ids":[source_id]}
    if kind!="historical":m["time"]=r.get("time","")
    k=key(m)
    if kind=="fixtures":
     if k in fixture and fixture[k].get("time")!=m.get("time"):
      rejects["conflicting_fixture_time"]+=1
      fixture[k]["time"]=""
     elif k not in fixture:fixture[k]=m
     accepted+=1
    elif values["gh"] is not None and values["ga"] is not None:
     raw_results.append({**m,**{c:v for c,v in values.items() if v is not None}});accepted+=1
    else:rejects["missing_full_time_score"]+=1
   report.append({"league":league,"kind":kind,"ok":True,"rows":len(rows),"accepted_rows":accepted,
     "rejected":dict(rejects),"source_id":source_id,"source_url":url,
     "content_sha256":hashlib.sha256(content.encode("utf-8")).hexdigest(),"fetched_at":now.isoformat()})
  except (ValueError,TypeError,KeyError) as exc:
   report.append({"league":league,"kind":kind,"ok":False,"source_url":url,"error":type(exc).__name__})
 hist,integrity=clean_history(raw_results,now)
 seen={key(r) for r in hist}
 upcoming=[local_fixture(m) for k,m in fixture.items() if future_match(m,now) and k not in seen]
 report.append({"league":"ALL","kind":"integrity","ok":not integrity["conflicting_events_quarantined"],**integrity})
 return hist,sorted(upcoming,key=key),sorted(report,key=lambda x:(x["league"],x["kind"]))
def wmean(rows,col,date,half_life_days=185):
 if isinstance(half_life_days,bool) or not math.isfinite(half_life_days) or half_life_days<=0:
  raise ValueError("half_life_days must be finite and positive")
 sw=0.; sy=0.
 for m in rows:
  age=max(0,(date-datetime.fromisoformat(m["date"]).date()).days)
  w=2**(-age/half_life_days)
  sw+=w; sy+=w*m[col]
 return sy/max(.001,sw),sw
def h2h_distribution(lamh,lama):
 """Independent Poisson 1X2 with negligible-tail truncation and normalized output."""
 if lamh is None or lama is None:return None
 if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0 for v in (lamh,lama)):
  raise ValueError("Goal intensities must be finite and nonnegative")
 if max(lamh,lama)>1000:raise ValueError("Goal intensities exceed numerical safety limit")
 def mass(lam):
  if lam==0:return [1.]
  limit=max(25,int(lam+12*math.sqrt(lam)+20))
  return [math.exp(-lam+k*math.log(lam)-math.lgamma(k+1)) for k in range(limit)]
 h,a=mass(lamh),mass(lama)
 ph=pd=pa=0.
 for i,hi in enumerate(h):
  for j,aj in enumerate(a):
   if i>j:ph+=hi*aj
   elif i==j:pd+=hi*aj
   else:pa+=hi*aj
 z=ph+pd+pa
 if z<=0:return None
 values={"home":round(ph/z,5),"draw":round(pd/z,5),"away":round(pa/z,5)}
 largest=max(values,key=values.get)
 values[largest]=round(1-sum(v for k,v in values.items() if k!=largest),5)
 return values

def market_rejection(hist,match,market):
 h,a,_,minimum=MARKETS[market]
 rows=[r for r in hist if r["league"]==match["league"] and r["date"]<match["date"]
   and number(r.get(h)) is not None and number(r.get(a)) is not None]
 nh=sum(norm(r["home"])==norm(match["home"]) for r in rows)
 na=sum(norm(r["away"])==norm(match["away"]) for r in rows)
 details={"n_league":len(rows),"n_home":nh,"n_away":na,"minimum_league":minimum,"minimum_team":3}
 if len(rows)<minimum:return {"code":"insufficient_league_history","message":"Istoric insuficient în ligă pentru această piață.",**details}
 if min(nh,na)<3:return {"code":"insufficient_team_history","message":"Istoric insuficient acasă/deplasare pentru cel puțin o echipă.",**details}
 return {"code":"invalid_league_mean","message":"Media ligii nu permite o estimare validă.",**details}

def pred(hist,match,market,half_life_days=185,prior_weight=7,opponent_effect=True):
 if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in (half_life_days,prior_weight)) or half_life_days<=0 or prior_weight<0:
  raise ValueError("Model decay must be positive and prior nonnegative, both finite")
 homecol,awaycol,line,minimum=MARKETS[market]
 relevant=[m for m in hist if m["league"]==match["league"] and m["date"]<match["date"]
  and number(m.get(homecol)) is not None and number(m.get(awaycol)) is not None]
 if len(relevant)<minimum: return None
 homeid,awayid=norm(match["home"]),norm(match["away"])
 home=[r for r in relevant if norm(r["home"])==homeid]
 away=[r for r in relevant if norm(r["away"])==awayid]
 if min(len(home),len(away))<3: return None
 date=datetime.fromisoformat(match["date"]).date()
 PRIOR_WEIGHT=prior_weight
 HALF_LIFE_DAYS=half_life_days
 baseh,_=wmean(relevant,homecol,date,HALF_LIFE_DAYS); basea,_=wmean(relevant,awaycol,date,HALF_LIFE_DAYS)
 if baseh<=0 or basea<=0: return None
 def shrunk(rows,col,avg):
  m,n=wmean(rows,col,date,HALF_LIFE_DAYS)
  return (m*n+PRIOR_WEIGHT*avg)/(n+PRIOR_WEIGHT)
 home_attack_raw,home_effective=wmean(home,homecol,date,HALF_LIFE_DAYS)
 opposing_home_conceded_raw,opposing_effective=wmean(away,homecol,date,HALF_LIFE_DAYS)
 away_attack_raw,away_effective=wmean(away,awaycol,date,HALF_LIFE_DAYS)
 opposing_away_conceded_raw,opposing_away_effective=wmean(home,awaycol,date,HALF_LIFE_DAYS)
 h_attack=shrunk(home,homecol,baseh)
 h_conceded=shrunk(away,homecol,baseh)
 a_attack=shrunk(away,awaycol,basea)
 a_conceded=shrunk(home,awaycol,basea)
 lamh=max(.05,min(baseh*2.4,math.sqrt(h_attack*h_conceded) if opponent_effect else h_attack))
 lama=max(.05,min(basea*2.4,math.sqrt(a_attack*a_conceded) if opponent_effect else a_attack))
 mu=lamh+lama
 totals=[r[homecol]+r[awaycol] for r in relevant]
 avg=sum(totals)/len(totals)
 variance=sum((v-avg)**2 for v in totals)/max(1,len(totals)-1)
 dispersion=max(1.,min(2.5,variance/max(.1,avg)))
 p=over_tail(mu,line,dispersion)
 explanation={
   "method_version":"weighted_opponent_model_v1" if half_life_days==185 and prior_weight==7 and opponent_effect else "research_variant",
   "opponent_effect":bool(opponent_effect),
   "pipeline_version":PIPELINE_VERSION,
   "status":"arithmetic_trace_not_causal_explanation",
   "source_families":sorted({v.split(":")[0] for r in relevant for v in r.get("source_ids",["unspecified_history"])}),
   "source_ids":sorted({v for r in relevant for v in r.get("source_ids",["unspecified_history"])}),
   "first_observation_date":min(r["date"] for r in relevant),
   "last_observation_date":max(r["date"] for r in relevant),
   "formulas":{
    "recency":"weight = 2 ** (-age_days / half_life_days)",
    "regularization":"shrunk = (weighted_mean * sum_weights + prior_pseudogames * league_mean) / (sum_weights + prior_pseudogames)",
    "combination":"lambda = sqrt(team_attack_shrunk * opponent_conceded_shrunk)" if opponent_effect else "lambda = team_attack_shrunk",
    "clipping":"lambda bounded to [0.05, 2.4 * league_mean]",
    "h2h":"sum independent Poisson score probabilities for home>away, equal, home<away; normalize",
    "total":"P(over line) = 1 - CDF(floor(line))"},
   "calibration_status":"unvalidated",
   "uncertainty":{"status":"not_quantified","probability_interval":None,
    "message":"Nu există un interval validat pentru probabilitatea individuală. Eșantionul, sursele și ipotezele modelului adaugă incertitudine; intervalele de scor din test nu sunt intervale pentru acest meci."},
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
  "n_away":len(away),"small_sample":min(len(home),len(away))<8 or min(home_effective,away_effective)<3 or len(relevant)<150,
  "status":"experimental",
  "quality":"very_low" if min(len(home),len(away))<8 or min(home_effective,away_effective)<3 or len(relevant)<150 else "unverified",
  "h2h":h2h_distribution(lamh,lama) if market=="goals" else None,
  "explanation":explanation}
def over_tail(mu,line,dispersion=1):
 if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in (mu,line,dispersion)) or mu<0 or line<0 or dispersion<1:
  raise ValueError("Mean and line must be finite nonnegative; dispersion must be finite >= 1")
 if mu==0:return 0.
 if line>100000 or mu>100000:raise ValueError("Count parameters exceed numerical safety limit")
 k=mu/(dispersion-1) if dispersion>1.07 else float("inf")
 term=(k/(k+mu))**k if math.isfinite(k) else math.exp(-mu)
 if term<1e-290:
  # Starting a recurrence at exp(-mu)==0 loses the entire probability mass.
  # Log PMFs retain mass around the mode for large finite means.
  def logpmf(n):
   if math.isfinite(k):
    return math.lgamma(n+k)-math.lgamma(k)-math.lgamma(n+1)+k*math.log(k/(k+mu))+n*math.log(mu/(k+mu))
   return -mu+n*math.log(mu)-math.lgamma(n+1)
  return max(0.,min(1.,1-math.fsum(math.exp(logpmf(n)) for n in range(int(math.floor(line))+1))))
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
  bucket=[(p,y) for p,b,y in preds if min(int(p*5),4)==lower//2]
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

def write_json_atomic(path,value):
 """A failed serialization or interrupted write must not destroy the last good file."""
 temporary=None
 try:
  with tempfile.NamedTemporaryFile(mode="w",encoding="utf-8",dir=path.parent,prefix=".valueradar-",delete=False) as f:
   temporary=Path(f.name)
   json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False)
   f.write("\n")
  temporary.replace(path)
 finally:
  if temporary is not None and temporary.exists():temporary.unlink()
def prospective_eligible(entry,played=None):
 created=timestamp(entry.get("created_at"))
 if not created:return False
 frozen=fixture_kickoff(entry)
 actual=fixture_kickoff(played) if played else None
 if frozen and actual and abs((frozen-actual).total_seconds())>60:return False
 kickoff=frozen or actual
 if kickoff:return created<kickoff.astimezone(timezone.utc)
 # Legacy records without time: only creation before the earliest possible
 # kickoff on that fixed-offset date proves they preceded the match.
 try:
  earliest=datetime.fromisoformat(entry["date"]).replace(tzinfo=timezone(timedelta(hours=1))).astimezone(timezone.utc)
  return created<earliest
 except (ValueError,KeyError,TypeError):return False
def valid_forecast_record(entry):
 try:
  required=("league","date","home","away","market","created_at","settled")
  if not isinstance(entry,dict) or not all(k in entry for k in required):return False
  if entry["league"] not in LEAGUES or not isinstance(entry["home"],str) or not isinstance(entry["away"],str):return False
  if not norm(entry["home"]) or not norm(entry["away"]) or norm(entry["home"])==norm(entry["away"]):return False
  if datetime.strptime(entry["date"],"%Y-%m-%d").date().isoformat()!=entry["date"]:return False
  if not isinstance(entry["settled"],bool) or timestamp(entry["created_at"]) is None:return False
  def probability(v):return not isinstance(v,bool) and isinstance(v,(int,float)) and math.isfinite(v) and 0<=v<=1
  if entry["market"]=="h2h":
   p=entry.get("probabilities")
   if not isinstance(p,dict) or set(p)!={"home","draw","away"} or not all(probability(v) for v in p.values()) or abs(sum(p.values())-1)>.00002:return False
   if entry["settled"] and entry.get("actual_outcome") not in p:return False
  elif entry["market"] in MARKETS:
   line=entry.get("line")
   if isinstance(line,bool) or not isinstance(line,(int,float)) or not math.isfinite(line) or line<0 or line%1!=.5:return False
   if not probability(entry.get("p_over")):return False
   if entry["settled"] and entry.get("actual_over") not in (0,1):return False
  else:return False
  return True
 except (ValueError,TypeError,KeyError):return False
MAX_HISTORY_AGE_DAYS=21

def market_availability(hist,league,market,at,report):
 """Operational freshness rule, separate from retrospective model arithmetic."""
 h,a,_,_=MARKETS[market]
 rows=[r for r in hist if r["league"]==league and number(r.get(h)) is not None and number(r.get(a)) is not None and r["date"]<=at.date().isoformat()]
 last=max((r["date"] for r in rows),default=None)
 age=(at.date()-datetime.fromisoformat(last).date()).days if last else None
 sources=[r for r in report if r.get("league")==league and r.get("kind")=="results"]
 failed=not sources or any(r.get("ok") is not True for r in sources)
 code="current_results_source_unavailable" if failed else "missing_history" if last is None else "history_too_old" if age>MAX_HISTORY_AGE_DAYS else "available"
 messages={"available":"Istoric recent disponibil; precizia modelului rămâne nevalidată.",
  "current_results_source_unavailable":"Sursa rezultatelor curente nu este disponibilă. Comparația este blocată.",
  "missing_history":"Nu există observații pentru această piață.",
  "history_too_old":"Istoricul are peste 21 de zile. Așteptăm rezultate recente, inclusiv după pauza dintre sezoane."}
 return {"status":code,"comparison_allowed":code=="available","message":messages[code],
  "last_observation_date":last,"history_age_days":age,"max_history_age_days":MAX_HISTORY_AGE_DAYS,
  "evaluated_at":at.isoformat(),"policy":"operational_guard_v1_not_statistically_validated"}

def comparison_allowed(prediction,at):
 """A recent execution timestamp cannot make old observations recent."""
 if not isinstance(prediction,dict):return False
 availability=prediction.get("availability")
 if availability is not None and (not isinstance(availability,dict) or availability.get("comparison_allowed") is not True):return False
 explanation=prediction.get("explanation")
 if not isinstance(explanation,dict):return False
 try:
  day=datetime.strptime(explanation["last_observation_date"],"%Y-%m-%d").date()
  return 0<=(at.astimezone(timezone.utc).date()-day).days<=MAX_HISTORY_AGE_DAYS
 except (KeyError,ValueError,TypeError):return False

def forecast_identity(entry):
 return (*key(entry),entry["market"],entry.get("line") if entry["market"]!="h2h" else None,entry.get("pipeline_version","legacy_unversioned"))

def prospective(hist,fixtures,run_at,source_report=()):
 """Append first forecasts, settle later. Never silently reset or truncate evidence."""
 path=OUT/"forecast_log.json"
 try:
  log=json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
 except (OSError,ValueError) as exc:
  raise RuntimeError("Forecast journal is unreadable; refusing to replace it") from exc
 if not isinstance(log,list) or any(not valid_forecast_record(r) for r in log):
  raise RuntimeError("Forecast journal schema is invalid; refusing to replace it")
 logkey=forecast_identity
 known={logkey(r) for r in log}
 if len(known)!=len(log):raise RuntimeError("Forecast journal has duplicate canonical identities; refusing to choose or rewrite evidence")
 now=timestamp(run_at)
 if now is None:raise ValueError("run_at must contain an explicit timezone")
 for f in fixtures:
  kickoff=fixture_kickoff(f)
  # New journal records require an explicit kickoff. Unknown times remain
  # visible as research but cannot provide prospective timing evidence.
  if kickoff is None or not future_match(f,now):continue
  base={k:f[k] for k in ("league","date","home","away")}
  base.update({"created_at":run_at,"settled":False,"kickoff_utc":kickoff.astimezone(timezone.utc).isoformat(),
    "forecast_schema_version":2,"pipeline_version":PIPELINE_VERSION,"calibration_status":"unvalidated"})
  for market,p in f["markets"].items():
   if p is None or p.get("availability",{}).get("comparison_allowed") is False:continue
   entry={**base,"market":market,"line":p["line"],"p_over":p["over"],
     "method_version":p.get("explanation",{}).get("method_version","unknown"),
     "historical_cutoff_exclusive":p.get("explanation",{}).get("historical_cutoff_exclusive",f["date"])}
   if logkey(entry) not in known:log.append(entry);known.add(logkey(entry))
  gp=f["markets"].get("goals")
  if gp and gp.get("h2h") and gp.get("availability",{}).get("comparison_allowed") is not False:
   entry={**base,"market":"h2h","probabilities":dict(gp["h2h"]),
     "method_version":gp.get("explanation",{}).get("method_version","unknown"),
     "historical_cutoff_exclusive":f["date"]}
   if logkey(entry) not in known:log.append(entry);known.add(logkey(entry))
 from settlement import state,freeze_result,audit
 valid_outcomes,outcome_integrity=clean_history(hist,now)
 outcomes={key(r):r for r in valid_outcomes}
 from score_evidence import archived_results
 conflicting={tuple(k) for k in outcome_integrity["conflicting_event_keys"]}
 for row in archived_results(log):
  if key(row) not in outcomes and key(row) not in conflicting:outcomes[key(row)]=row
 for league,date,home,away in conflicting:
  outcomes[(league,date,home,away)]={"league":league,"date":date,"home":home,"away":away,"result_conflict":True}
 for r in log:
  if r.get("settled"):continue
  played=outcomes.get(key(r))
  if not played:continue
  status=state(r,played,now)
  if status=="blocked_creation_evidence":r.setdefault("evaluation_exclusion","creation_not_provably_before_kickoff")
  if status=="ready_to_settle":freeze_result(r,played,now,source_report)
 # Append order is part of the audit trail; retaining the full evidence avoids
 # outcome-dependent expiry of successful or unsuccessful predictions.
 if any(not valid_forecast_record(r) for r in log):raise ValueError("Generated forecast journal contains invalid probabilities or settlement data")
 write_json_atomic(path,log)
 write_json_atomic(OUT/"settlement_report.json",audit(log,outcomes,now,outcome_integrity))
 scores={}
 for market in list(MARKETS)+["h2h"]:
  settled=[r for r in log if r.get("settled") and r["market"]==market]
  done=[];seen=set()
  for r in settled:
   k=logkey(r)
   if k in seen or state(r,outcomes.get(key(r)),now)!="settled_with_evidence":continue
   seen.add(k);done.append(r)
  if market=="h2h":
   def error(r):
    return sum((r["probabilities"][k]-float(r["actual_outcome"]==k))**2 for k in ("home","draw","away"))/3
  else:
   def error(r):return (r["p_over"]-r["actual_over"])**2
  scores[market]={"n":len(done),"brier":round(sum(error(r) for r in done)/len(done),5) if done else None,
   "excluded_nonprospective_or_duplicate":len(settled)-len(done),
   "by_pipeline_version":{version:{"n":sum(r.get("pipeline_version","legacy_unversioned")==version for r in done),
     "brier":round(sum(error(r) for r in done if r.get("pipeline_version","legacy_unversioned")==version)/sum(r.get("pipeline_version","legacy_unversioned")==version for r in done),5)}
    for version in sorted({r.get("pipeline_version","legacy_unversioned") for r in done})},
   "notice":"Mixed versions are descriptive only; use by_pipeline_version for version-specific evaluation."}
 return scores,len(log)

def run(imported=None,run_at=None,settlement_results=()):
 OUT.mkdir(parents=True,exist_ok=True)
 at=run_at or datetime.now(timezone.utc)
 if isinstance(at,str):at=timestamp(at)
 if at is None or at.tzinfo is None:raise ValueError("run_at requires a timezone")
 at=at.astimezone(timezone.utc)
 hist,fixtures,report=imported if imported is not None else load_all(at)
 if len(hist)<100 or not fixtures:
  print("Insufficient data; preserving existing dashboard.",file=sys.stderr)
  return 2
 today=at.date()
 upcoming=[m for m in fixtures if future_match(m,at) and m["date"] <= (today+timedelta(days=30)).isoformat()]
 health={lg:{mk:market_availability(hist,lg,mk,at,report) for mk in MARKETS} for lg in LEAGUES}
 enriched=[]
 for m in upcoming:
  markets={k:pred(hist,m,k) for k in MARKETS}
  for mk,p in markets.items():
   if p is not None:
    p["availability"]=health[m["league"]][mk]
    if not p["availability"]["comparison_allowed"]:p["quality"]="very_low"
  enriched.append({**m,"markets":markets,"market_rejections":{k:market_rejection(hist,m,k) for k,p in markets.items() if p is None}})
 stamp=max(at,datetime.now(timezone.utc)).isoformat()
 # Supplementary observations are evaluation-only: no training, predictions,
 # freshness indicators or retrospective holdout ever consume these rows.
 external_sources=[{"ok":True,"league":row["league"],"kind":"settlement_only","source_id":row["source_ids"][0],
   "content_sha256":row["settlement_observation"]["observation_sha256"],"fetched_at":row["settlement_observation"]["verified_at"]}
   for row in settlement_results]
 prospective_report,count=prospective([*hist,*settlement_results],enriched,stamp,[*report,*external_sources])
 audit={lg:{market:sum(r["league"]==lg and r.get(h) is not None and r.get(a) is not None for r in hist)
  for market,(h,a,_,_) in MARKETS.items()} for lg in LEAGUES}
 freshness={lg:{market:max((r["date"] for r in hist if r["league"]==lg and r.get(h) is not None and r.get(a) is not None),default=None)
  for market,(h,a,_,_) in MARKETS.items()} for lg in LEAGUES}
 payload={"version":"1.0","pipeline_version":PIPELINE_VERSION,"generated_at":stamp,
  "methodology":{"version":"weighted_opponent_model_v1",
   "approach":"Time-decayed team and opponent rates, shrunk toward league means, with geometric combination.",
   "prior_pseudogames":7,"half_life_days":185,
   "limitations":"No referees, lineup, tactical events, or validated ROI.",
   "details":"See ANALYSIS_METHODOLOGY.md"},"history_rows":len(hist),
  "fixture_rows":len(fixtures),"source_success":sum(r["ok"] for r in report if r["kind"]!="integrity"),
  "source_total":sum(r["kind"]!="integrity" for r in report),
  "source_report":[r for r in report if r["kind"]!="integrity"],
  "data_integrity":next((r for r in report if r["kind"]=="integrity"),{}),"data_audit":audit,
  "last_stat_date":freshness,"data_health":health,
  "backtest":{**{m:validation(hist,m) for m in MARKETS},"h2h":validation_h2h(hist)},
  "prospective":prospective_report,"prospective_predictions_recorded":count,
  "fixtures":enriched,"message":"Experimental model. International odds monitored separately; no verified Romanian bookmaker prices or validated value bets."}
 write_json_atomic(OUT/"latest.json",payload)
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
 alternative=pred(demo,{"league":"Ligue 1","date":"2026-07-01","home":"A","away":"B"},
  "goals",half_life_days=90,prior_weight=15,opponent_effect=False)
 assert alternative is not None and alternative["explanation"]["method_version"]=="research_variant"
 assert alternative["explanation"]["prior_pseudogames"]==15
 print("Self-tests passed.")
if __name__=="__main__":
 sys.exit((selftest() or 0) if "--self-test" in sys.argv else run())
