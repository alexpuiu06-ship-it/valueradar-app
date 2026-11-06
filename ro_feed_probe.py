#!/usr/bin/env python3
"""Bounded PropLine evaluation. Saves aggregate diagnostics, never raw odds or bets."""
from collections import Counter
from datetime import datetime, timezone
import argparse
import copy
import json
import math
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

import odds_scanner as odds
import runner

API="https://api.prop-line.com/v1"
BOOKS=("superbet_ro","netbet_ro")
REPORT=Path(__file__).resolve().parent/"work"/"ro_feed_preflight.json"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError("Provider redirects are not accepted")


def fetch(path,key=None):
    # Key is an HTTP header; neither URLs, headers nor exception strings are logged.
    headers={"User-Agent":"ValueRadar-provider-evaluation/1.0"}
    if key:headers["X-API-Key"]=key
    request=urllib.request.Request(API+path,headers=headers)
    try:
        opener=urllib.request.build_opener(NoRedirect())
        with opener.open(request,timeout=15) as response:
            raw=response.read(3000001)
            if len(raw)>3000000:return None,{},"response_size_limit"
            return json.loads(raw.decode("utf-8")),dict(response.headers.items()),None
    except urllib.error.HTTPError as exc:return None,{},f"http_{exc.code}"
    except Exception as exc:return None,{},type(exc).__name__


def american_decimal(value):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not float(value).is_integer() or abs(value)<100:
        raise ValueError("Expected finite integer American odds")
    price=1+value/100 if value>0 else 1+100/abs(value)
    if not 1<price<=1000:raise ValueError("Unsupported decimal price")
    return price


def summarize_health(payload):
    if not isinstance(payload,dict) or not isinstance(payload.get("bookmakers"),list):
        raise ValueError("Unexpected public health schema")
    rows=[]
    for name in BOOKS:
        matches=[x for x in payload["bookmakers"] if isinstance(x,dict) and x.get("key")==name]
        row=matches[0] if len(matches)==1 else {}
        rows.append({"bookmaker":name,"present":bool(row),"latest_provider_update":row.get("latest_update"),
          "provider_reports_stale":row.get("is_stale"),"provider_market_count":row.get("market_count"),
          "warning":"Global operational metric; does not establish freshness of an individual football price."})
    return {"provider_as_of":payload.get("as_of"),"books":rows}


def assess(payload,fixtures,league,at):
    if not isinstance(payload,list):raise ValueError("Expected the documented bulk odds array")
    rejected=Counter();by_book=Counter();matches=Counter();seen=set()
    event_ids=Counter(e.get("id") for e in payload if isinstance(e,dict) and isinstance(e.get("id"),str))
    for event in payload:
        if not isinstance(event,dict):rejected["invalid_event"]+=1;continue
        if any(not isinstance(event.get(k),str) or not event[k] for k in ("id","home_team","away_team","commence_time")):
            rejected["invalid_identity"]+=1;continue
        if event_ids[event["id"]]!=1:rejected["duplicate_event_id"]+=1;continue
        if event.get("sport_key")!=odds.SPORTS[league] or event.get("live") is not False or event.get("is_outright") is not False:
            rejected["not_explicitly_pre_match_football"]+=1;continue
        identity=(event.get("id"),event.get("home_team"),event.get("away_team"),event.get("commence_time"))
        if identity in seen:rejected["duplicate_event"]+=1;continue
        seen.add(identity)
        start=odds.dt(event.get("commence_time"))
        if not start or start<=at:rejected["unknown_or_started"]+=1;continue
        books=event.get("bookmakers")
        if not isinstance(books,list):rejected["invalid_books"]+=1;continue
        counts=Counter(b.get("key") for b in books if isinstance(b,dict) and isinstance(b.get("key"),str))
        fixture=odds.match_event(event,[f for f in fixtures if isinstance(f,dict) and f.get("league")==league],at)
        for book in books:
            if not isinstance(book,dict) or book.get("key") not in BOOKS:continue
            name=book["key"]
            if counts[name]!=1:rejected["duplicate_book"]+=1;continue
            if book.get("pregame_only") is True:rejected["frozen_book"]+=1;continue
            markets=book.get("markets")
            choices=[m for m in markets if isinstance(m,dict) and m.get("key")=="h2h"] if isinstance(markets,list) else []
            if len(choices)!=1:rejected["missing_or_duplicate_h2h"]+=1;continue
            market=choices[0]
            updated=odds.dt(market.get("last_update"))
            if not updated or not 0<=(at-updated).total_seconds()<=120:
                rejected["market_not_recent"]+=1;continue
            if market.get("period") is not None or market.get("team") is not None or market.get("suspended_at") is not None or market.get("line_type","main")!="main":
                rejected["period_line_or_suspension"]+=1;continue
            outcomes=market.get("outcomes")
            if not isinstance(outcomes,list) or len(outcomes)!=3:
                rejected["incomplete_h2h"]+=1;continue
            target=copy.deepcopy(market)
            normalized={"key":name,"markets":[target]}
            try:
                for value in target["outcomes"]:
                    seen_at=odds.dt(value.get("last_seen_at"))
                    if not seen_at or not 0<=(at-seen_at).total_seconds()<=120:raise ValueError
                    value["price"]=american_decimal(value.get("price"))
                if odds.parse_h2h(normalized,event,at) is None:raise ValueError
            except (ValueError,TypeError,AttributeError):
                rejected["invalid_prices_or_selection_freshness"]+=1;continue
            by_book[name]+=1
            if fixture and runner.comparison_allowed((fixture.get("markets",{}).get("goals")),at):matches[name]+=1
    return {"events_received":len(payload),"complete_recent_markets":dict(by_book),
      "matched_current_model_markets":dict(matches),"rejection_counts":dict(rejected),
      "price_format":"documented_American_converted_to_decimal",
      "raw_odds_saved":False,"operator_prices_independently_verified":False,"verified_value":False}


def run(authenticated=False,league="Premier League",output=REPORT):
    if league not in odds.SPORTS:raise ValueError("Unsupported league")
    report={"provider":"PropLine","checked_at":datetime.now(timezone.utc).isoformat(),"mode":"authenticated" if authenticated else "public_health",
      "requested_books":list(BOOKS),"publisher_declared_jurisdiction":"RO",
      "operator_prices_independently_verified":False,"verified_value":False,
      "value_blockers":odds.value_blockers(),"raw_odds_saved":False}
    status=0
    if not authenticated:
        data,_,error=fetch("/freshness")
        if error:report.update(status="public_health_error",error=error);status=2
        else:
            try:report.update(status="public_health_only_not_quote_validation",public_health=summarize_health(data))
            except ValueError:report.update(status="invalid_schema");status=2
    else:
        key=os.getenv("PROPLINE_API_KEY","").strip()
        if not key:report.update(status="needs_api_key",message="Add PROPLINE_API_KEY to GitHub Actions Secrets; never send it in chat.");status=2
        else:
            try:latest=json.loads((runner.OUT/"latest.json").read_text())
            except (OSError,ValueError):latest={}
            if not isinstance(latest,dict):latest={}
            generated=odds.dt(latest.get("generated_at"));at=datetime.now(timezone.utc)
            if not generated or not 0<=(at-generated).total_seconds()<=12*3600 or not isinstance(latest.get("fixtures"),list):
                report.update(status="stale_analysis");status=2
            else:
                query=urllib.parse.urlencode({"markets":"h2h","bookmakers":",".join(BOOKS),"max_age":120})
                data,headers,error=fetch(f"/sports/{odds.SPORTS[league]}/odds?{query}",key)
                report["authenticated_requests"]=1
                report["daily_quota_headers"]={k.lower():int(v) for k,v in headers.items() if k.lower() in ("x-daily-limit","x-daily-used","x-daily-remaining") and str(v).isdigit() and len(str(v))<=10}
                if error:report.update(status="provider_error",error=error);status=2
                else:
                    try:
                        report["quality"]=assess(data,latest.get("fixtures",[]),league,datetime.now(timezone.utc))
                        complete=all(report["quality"]["matched_current_model_markets"].get(book,0)>0 for book in BOOKS)
                        report["status"]="diagnostic_only" if complete else "incomplete_quote_validation"
                        if not complete:status=2
                    except ValueError:report.update(status="invalid_schema");status=2
    output.parent.mkdir(parents=True,exist_ok=True)
    runner.write_json_atomic(output,report)
    print("RO feed evaluation:",report["status"],"; verified value: false; raw odds saved: false")
    return status


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authenticated",action="store_true")
    parser.add_argument("--league",choices=odds.SPORTS,default=os.getenv("PROBE_LEAGUE","Premier League"))
    args=parser.parse_args()
    raise SystemExit(run(args.authenticated or os.getenv("AUTHENTICATED_PROBE")=="true",args.league))
