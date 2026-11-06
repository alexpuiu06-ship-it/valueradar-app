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
import tempfile
import urllib.error
import urllib.parse
import urllib.request

import odds_scanner as odds
import runner

API="https://api.prop-line.com/v1"
BOOKS=("superbet_ro","netbet_ro")
MAX_QUOTE_AGE_SECONDS=120
REPORT=Path(__file__).resolve().parent/"work"/"ro_feed_preflight.json"
QUALITY_COUNTS=("events_received","books_received","complete_recent_markets","matched_current_model_markets",
                "book_diagnostics","rejection_counts","book_status_scope")


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
    if league not in odds.SPORTS or at.tzinfo is None:raise ValueError("Expected a supported league and explicit timezone")
    rejected=Counter();by_book=Counter();matches=Counter();received=Counter()
    book_rejections={name:Counter() for name in BOOKS}
    candidates=[f for f in fixtures if isinstance(f,dict) and f.get("league")==league
      and all(isinstance(f.get(k),str) and f[k] for k in ("date","home","away"))] if isinstance(fixtures,list) else []

    def event_books(event):
        books=event.get("bookmakers",[]) if isinstance(event,dict) else []
        return [b["key"] for b in books if isinstance(b,dict) and b.get("key") in BOOKS] if isinstance(books,list) else []

    def reject(reason,name=None,affected=()):
        rejected[reason]+=1
        for book in (name,) if name else set(affected):book_rejections[book][reason]+=1

    def event_identity(event):
        if not isinstance(event,dict) or any(not isinstance(event.get(k),str) or not event[k].strip()
          for k in ("id","home_team","away_team","commence_time")):return None
        home,away=odds.canonical(event["home_team"]),odds.canonical(event["away_team"])
        start=odds.dt(event["commence_time"])
        if not home or not away or home==away or not start:return None
        # Provider IDs and spelling are not independent football events.
        return (event.get("sport_key"),home,away,start)

    event_ids=Counter(e.get("id") for e in payload if isinstance(e,dict) and isinstance(e.get("id"),str))
    canonical_ids=Counter(identity for event in payload if (identity:=event_identity(event)) is not None
      and isinstance(identity[0],str))
    mapped={}
    fixture_counts=Counter()
    for index,event in enumerate(payload):
        if event_identity(event) is None:continue
        fixture=odds.match_event(event,candidates,at)
        if fixture is not None:mapped[index]=fixture;fixture_counts[runner.key(fixture)]+=1
    samples={};selection_samples=[]
    for index,event in enumerate(payload):
        affected=event_books(event);received.update(affected)
        if not isinstance(event,dict):reject("invalid_event");continue
        identity=event_identity(event)
        if identity is None:reject("invalid_identity_or_kickoff",affected=affected);continue
        if event_ids[event["id"]]!=1:reject("duplicate_event_id",affected=affected);continue
        if event.get("sport_key")!=odds.SPORTS[league] or event.get("live") is not False or event.get("is_outright") is not False:
            reject("not_explicitly_pre_match_football",affected=affected);continue
        fixture=mapped.get(index)
        if canonical_ids[identity]>1 or (fixture is not None and fixture_counts[runner.key(fixture)]>1):
            reject("duplicate_canonical_event",affected=affected);continue
        start=identity[3]
        if start<=at:reject("already_started",affected=affected);continue
        books=event.get("bookmakers")
        if not isinstance(books,list):reject("invalid_books");continue
        counts=Counter(b.get("key") for b in books if isinstance(b,dict) and isinstance(b.get("key"),str))
        for book in books:
            if not isinstance(book,dict) or book.get("key") not in BOOKS:continue
            name=book["key"]
            if counts[name]!=1:reject("duplicate_book",name);continue
            if book.get("pregame_only") is True:reject("frozen_book",name);continue
            markets=book.get("markets")
            choices=[m for m in markets if isinstance(m,dict) and m.get("key")=="h2h"] if isinstance(markets,list) else []
            if len(choices)!=1:reject("missing_or_duplicate_h2h",name);continue
            market=choices[0]
            updated=odds.dt(market.get("last_update"))
            if not updated:
                reject("missing_market_timestamp" if market.get("last_update") is None else "invalid_market_timestamp",name);continue
            age=(at-updated).total_seconds()
            if not 0<=age<=MAX_QUOTE_AGE_SECONDS:
                reject("future_market_timestamp" if age<0 else "stale_market_timestamp",name);continue
            if market.get("period") is not None or market.get("team") is not None or market.get("suspended_at") is not None or market.get("line_type","main")!="main":
                reject("period_line_or_suspension",name);continue
            outcomes=market.get("outcomes")
            if not isinstance(outcomes,list) or len(outcomes)!=3:
                reject("incomplete_h2h",name);continue
            target=copy.deepcopy(market)
            normalized={"key":name,"markets":[target]}
            invalid=None;selection_ids=set()
            try:
                for value in target["outcomes"]:
                    if not isinstance(value,dict):invalid="invalid_selection_shape";break
                    if not isinstance(value.get("name"),str) or not value["name"].strip():invalid="invalid_selection_name";break
                    side="draw" if value["name"].casefold() in ("draw","tie","x") else (
                      "home" if odds.canonical(value["name"])==identity[1] else "away" if odds.canonical(value["name"])==identity[2] else None)
                    if side is None:
                        invalid="unsupported_selection_identity"
                        if len(selection_samples)<3:
                            selection_samples.append({"bookmaker":name,"home":event["home_team"][:120],
                              "away":event["away_team"][:120],"selection_name":value["name"][:120]})
                        break
                    if side in selection_ids:invalid="duplicate_selection_identity";break
                    selection_ids.add(side)
                    if value.get("line_type") not in (None,"main") or value.get("point") is not None:
                        invalid="unsupported_selection_line";break
                    seen_at=odds.dt(value.get("last_seen_at"))
                    if not seen_at:
                        invalid="missing_selection_timestamp" if value.get("last_seen_at") is None else "invalid_selection_timestamp";break
                    age=(at-seen_at).total_seconds()
                    if not 0<=age<=MAX_QUOTE_AGE_SECONDS:
                        invalid="future_selection_timestamp" if age<0 else "stale_selection_timestamp";break
                    try:value["price"]=american_decimal(value.get("price"))
                    except (ValueError,TypeError,OverflowError):invalid="invalid_american_price";break
                if invalid is None and odds.parse_h2h(normalized,event,at) is None:invalid="invalid_h2h_prices_or_margin"
            except (ValueError,TypeError,AttributeError,OverflowError):invalid="invalid_h2h_market"
            if invalid:reject(invalid,name);continue
            by_book[name]+=1
            if fixture is None:
                reject("fixture_identity_or_kickoff_not_matched",name)
                # A maximum of three identity-only examples diagnoses aliases or
                # schedule differences without exporting prices or a feed corpus.
                if identity not in samples and len(samples)<3:
                    same_pair=[f for f in candidates if odds.canonical(f["home"])==identity[1] and odds.canonical(f["away"])==identity[2]]
                    samples[identity]={"provider_event_id":event["id"][:120],"home":event["home_team"][:120],"away":event["away_team"][:120],
                      "commence_time":start.isoformat(),"candidate_kickoffs_utc":sorted({t.astimezone(timezone.utc).isoformat() for f in same_pair if (t:=runner.fixture_kickoff(f)) is not None})[:2]}
                continue
            model=fixture.get("markets",{}).get("goals") if isinstance(fixture.get("markets"),dict) else None
            if not isinstance(model,dict) or not odds.valid_probabilities(model.get("h2h")):
                reject("invalid_or_missing_model_h2h",name);continue
            if not runner.comparison_allowed(model,at):reject("model_history_not_current",name);continue
            matches[name]+=1
    diagnostics={}
    for name in BOOKS:
        status=("absent" if not received[name] else "received_but_rejected" if not by_book[name] else
          "complete_markets_without_model_match" if not matches[name] else "partially_matched" if matches[name]<by_book[name] else "matched_current_model")
        diagnostics[name]={"status":status,"received_blocks":received[name],"complete_recent_markets":by_book[name],
          "matched_current_model_markets":matches[name],"rejection_counts":dict(book_rejections[name])}
    return {"events_received":len(payload),"complete_recent_markets":dict(by_book),
      "matched_current_model_markets":dict(matches),"rejection_counts":dict(rejected),
      "books_received":{name:received[name] for name in BOOKS},"book_diagnostics":diagnostics,
      "book_status_scope":"Presence in this filtered response only; absence does not establish provider coverage or account entitlement.",
      "unmatched_fixture_samples":list(samples.values()),"sample_policy":"At most three event identities/kickoffs; no prices or raw response retained.",
      "unsupported_selection_samples":selection_samples,
      "price_format":"documented_American_converted_to_decimal",
      "raw_odds_saved":False,"operator_prices_independently_verified":False,"verified_value":False}


def run(authenticated=False,league="Premier League",output=REPORT,inspect_stale=False):
    if league not in odds.SPORTS:raise ValueError("Unsupported league")
    request_max_age=3600 if inspect_stale else MAX_QUOTE_AGE_SECONDS
    report={"provider":"PropLine","league":league,"checked_at":datetime.now(timezone.utc).isoformat(),"mode":"authenticated" if authenticated else "public_health",
      "received_at":None,"analysis_generated_at":None,"model_pipeline_version":None,"max_quote_age_seconds":MAX_QUOTE_AGE_SECONDS,
      "requested_max_delivery_age_seconds":request_max_age,
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
            report["analysis_generated_at"]=generated.isoformat() if generated else None
            report["model_pipeline_version"]=latest.get("pipeline_version") if isinstance(latest.get("pipeline_version"),str) else None
            if not generated or not 0<=(at-generated).total_seconds()<=12*3600 or not isinstance(latest.get("fixtures"),list):
                report.update(status="stale_analysis");status=2
            else:
                query=urllib.parse.urlencode({"markets":"h2h","bookmakers":",".join(BOOKS),"max_age":request_max_age})
                data,headers,error=fetch(f"/sports/{odds.SPORTS[league]}/odds?{query}",key)
                received_at=datetime.now(timezone.utc)
                report["received_at"]=received_at.isoformat() if not error else None
                report["authenticated_requests"]=1
                report["daily_quota_headers"]={k.lower():int(v) for k,v in headers.items() if k.lower() in ("x-daily-limit","x-daily-used","x-daily-remaining") and str(v).isdigit() and len(str(v))<=10}
                if error:report.update(status="provider_error",error=error);status=2
                else:
                    try:
                        report["quality"]=assess(data,latest.get("fixtures",[]),league,received_at)
                        complete=all(report["quality"]["matched_current_model_markets"].get(book,0)>0 for book in BOOKS)
                        report["status"]="diagnostic_only" if complete else "incomplete_quote_validation"
                        if not complete:status=2
                    except ValueError:report.update(status="invalid_schema");status=2
    output.parent.mkdir(parents=True,exist_ok=True)
    runner.write_json_atomic(output,report)
    # A fixed whitelist is safe to copy from CI logs; never log payloads,
    # request headers, credentials or exception text from the provider.
    summary={"league":league,"status":report["status"],"received_at":report["received_at"],
      "analysis_generated_at":report["analysis_generated_at"],"max_quote_age_seconds":MAX_QUOTE_AGE_SECONDS,
      "requested_max_delivery_age_seconds":request_max_age,"quality":report.get("quality"),"quota":report.get("daily_quota_headers",{})}
    print("RO_FEED_DIAGNOSTIC "+json.dumps(summary,ensure_ascii=False,allow_nan=False))
    return status


def monitor(output=None):
    """One bounded pass, no retry or raw-price archive; provider failures stay visible."""
    report={"schema_version":1,"provider":"PropLine","max_quote_age_seconds":MAX_QUOTE_AGE_SECONDS,
      "requested_books":list(BOOKS),"operator_prices_independently_verified":False,
      "verified_value":False,"raw_odds_saved":False,"authenticated_requests":0,"leagues":[]}
    with tempfile.TemporaryDirectory(prefix="valueradar-ro-") as folder:
        for league in odds.SPORTS:
            row={"league":league,"status":"diagnostic_error","received_at":None,"analysis_generated_at":None,
              "requested_max_delivery_age_seconds":MAX_QUOTE_AGE_SECONDS,"quality":None,"quota":{}}
            try:
                path=Path(folder)/"report.json"
                path.unlink(missing_ok=True)
                run(authenticated=True,league=league,output=path)
                result=json.loads(path.read_text())
                for field in ("status","received_at","analysis_generated_at","requested_max_delivery_age_seconds"):
                    if field in result:row[field]=result[field]
                quality=result.get("quality")
                if isinstance(quality,dict):row["quality"]={k:quality[k] for k in QUALITY_COUNTS if k in quality}
                row["quota"]=result.get("daily_quota_headers",{})
                if "error" in result:row["error"]=result["error"]
                if report["authenticated_requests"] is not None:
                    report["authenticated_requests"]+=result.get("authenticated_requests",0)
            except Exception as exc:
                # An internal error must not reuse a previous league's successful
                # report or leak response/credential text through an exception.
                row["error"]=type(exc).__name__
                report["authenticated_requests"]=None
            report["leagues"].append(row)
    report["generated_at"]=datetime.now(timezone.utc).isoformat()
    runner.write_json_atomic(output or runner.OUT/"ro_feed_status.json",report)
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authenticated",action="store_true")
    parser.add_argument("--inspect-stale",action="store_true",help="Inspect up to 1 hour delivery history; accepted quote age remains 120 seconds")
    parser.add_argument("--league",choices=odds.SPORTS,default=os.getenv("PROBE_LEAGUE","Premier League"))
    args=parser.parse_args()
    raise SystemExit(run(args.authenticated or os.getenv("AUTHENTICATED_PROBE")=="true",args.league,
                         inspect_stale=args.inspect_stale or os.getenv("INSPECT_STALE")=="true"))
