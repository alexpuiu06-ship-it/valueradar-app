#!/usr/bin/env python3
"""Bounded aggregate-only OddsPapi evaluation. Price changes never prove freshness."""
from collections import Counter
from datetime import datetime, timedelta, timezone
import argparse
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request

import odds_scanner as odds
import runner
from ro_feed_probe import NoRedirect

API="https://api.oddspapi.io/v4"
BOOKS=("superbet.ro","betano.ro")
# Revalidated against the authenticated catalog before any odds request.
TOURNAMENTS={"Premier League":(17,"england",("premier-league",)),
 "La Liga":(8,"spain",("laliga","la-liga")),"Serie A":(23,"italy",("serie-a",)),
 "Bundesliga":(35,"germany",("bundesliga","1-bundesliga")),
 "Ligue 1":(34,"france",("ligue-1","ligue-1-mcdonalds"))}
REPORT=Path(__file__).resolve().parent/"work"/"oddspapi_preflight.json"


class ProbeError(Exception):
    pass


def fetch(path,params,key):
    # This provider requires a query credential. Never log URL/response/error text.
    if path not in ("/account","/tournaments","/markets","/fixtures","/odds"):
        return None,"unsupported_endpoint"
    url=API+path+"?"+urllib.parse.urlencode({**params,"apiKey":key})
    try:
        request=urllib.request.Request(url,headers={"User-Agent":"ValueRadar-provider-evaluation/1.0"})
        with urllib.request.build_opener(NoRedirect()).open(request,timeout=15) as response:
            # The unfiltered global market dictionary is considerably larger
            # than a fixture response. Both have explicit memory/network bounds.
            limit=32*1024*1024 if path=="/markets" else 5000000
            raw=response.read(limit+1)
            if len(raw)>limit:return None,"response_size_limit"
            return json.loads(raw.decode("utf-8")),None
    except urllib.error.HTTPError as exc:return None,f"http_{exc.code}"
    except Exception as exc:return None,type(exc).__name__


def integer(value):
    return isinstance(value,int) and not isinstance(value,bool) and value>=0


def account_summary(payload):
    # The raw account response echoes api_key and account/subscription identifiers.
    if not isinstance(payload,dict) or not isinstance(payload.get("subscriptions"),list):raise ProbeError("invalid_account_schema")
    current=payload.get("current_subscription_id")
    active=[s for s in payload["subscriptions"] if isinstance(s,dict) and s.get("is_active") is True
            and (current is None or s.get("subscription_id")==current)]
    if len(active)!=1:raise ProbeError("ambiguous_or_inactive_subscription")
    row=active[0];limit=row.get("request_limit");used=row.get("request_count")
    if not integer(limit) or not integer(used) or used>limit:raise ProbeError("invalid_quota")
    books=row.get("bookmakers");sports=row.get("sport_ids")
    if not isinstance(books,dict) or not isinstance(sports,list):raise ProbeError("invalid_entitlements")
    return {"request_limit":limit,"request_count":used,"remaining":limit-used,
      "soccer_included":10 in sports,"requested_books_included":{book:book in books for book in BOOKS}}


def market_definition(payload):
    if not isinstance(payload,list):raise ProbeError("invalid_markets_catalog")
    selected=[m for m in payload if isinstance(m,dict) and m.get("sportId")==10 and m.get("marketType")=="1x2"
      and m.get("period")=="fulltime" and m.get("playerProp") is False and m.get("handicap")==0 and m.get("marketLength")==3]
    if len(selected)!=1:raise ProbeError("ambiguous_full_time_1x2_catalog")
    market=selected[0];outcomes=market.get("outcomes")
    if not integer(market.get("marketId")) or not isinstance(outcomes,list) or len(outcomes)!=3:raise ProbeError("invalid_1x2_catalog")
    sides={}
    for row in outcomes:
        if not isinstance(row,dict) or row.get("outcomeName") not in ("1","X","2") or not integer(row.get("outcomeId")):
            raise ProbeError("invalid_1x2_outcome_catalog")
        side={"1":"home","X":"draw","2":"away"}[row["outcomeName"]]
        if side in sides or str(row["outcomeId"]) in sides.values():raise ProbeError("duplicate_1x2_catalog")
        sides[side]=str(row["outcomeId"])
    return str(market["marketId"]),sides


def verified_tournaments(payload,leagues):
    if not isinstance(payload,list):raise ProbeError("invalid_tournament_catalog")
    result={}
    for league in leagues:
        ident,category,slugs=TOURNAMENTS[league]
        rows=[r for r in payload if isinstance(r,dict) and r.get("tournamentId")==ident]
        result[league]=len(rows)==1 and rows[0].get("categorySlug")==category and rows[0].get("tournamentSlug") in slugs
    return result


def event(row,league,at):
    if not isinstance(row,dict) or row.get("sportId")!=10 or row.get("tournamentId")!=TOURNAMENTS[league][0] or\
       row.get("statusId")!=0 or isinstance(row.get("statusId"),bool) or row.get("statusName")!="Pre-Game" or row.get("hasOdds") is not True:
        return None
    if row.get("trueStartTime") is not None or row.get("trueEndTime") is not None:return None
    if any(not isinstance(row.get(k),str) or not row[k].strip() for k in ("fixtureId","participant1Name","participant2Name")):return None
    if not all(integer(row.get(k)) and row[k]>0 for k in ("participant1Id","participant2Id")) or row["participant1Id"]==row["participant2Id"]:return None
    start=odds.dt(row.get("startTime"))
    if not start or not at<start<=at+timedelta(days=30):return None
    return {"id":row["fixtureId"],"sport_key":odds.SPORTS[league],"commence_time":start.astimezone(timezone.utc).isoformat(),
            "home_team":row["participant1Name"],"away_team":row["participant2Name"]}


def choose_fixture(payload,fixtures,league,at):
    if not isinstance(payload,list):raise ProbeError("invalid_fixtures_schema")
    candidates=[];ids=Counter(row.get("fixtureId") for row in payload if isinstance(row,dict) and isinstance(row.get("fixtureId"),str))
    canonical=Counter();matched=Counter()
    for row in payload:
        e=event(row,league,at)
        if e is None:continue
        f=odds.match_event(e,[x for x in fixtures if x.get("league")==league],at)
        identity=(odds.canonical(e["home_team"]),odds.canonical(e["away_team"]),e["commence_time"])
        canonical[identity]+=1
        if f is not None:matched[runner.key(f)]+=1
        candidates.append((row,e,f,identity))
    eligible=[]
    for row,e,f,identity in candidates:
        if f is None or ids[e["id"]]!=1 or canonical[identity]!=1 or matched[runner.key(f)]!=1:continue
        model=(f.get("markets") or {}).get("goals")
        if not isinstance(model,dict) or not odds.valid_probabilities(model.get("h2h")) or not runner.comparison_allowed(model,at):continue
        eligible.append(row)
    eligible.sort(key=lambda row:(row["startTime"],row["fixtureId"]))
    return (eligible[0] if eligible else None),len(eligible)


def assess(payload,selected,fixtures,league,definition,at):
    e=event(payload,league,at);expected=event(selected,league,at)
    if e is None or expected is None or e!=expected or any(payload.get(k)!=selected.get(k) for k in ("participant1Id","participant2Id")):
        raise ProbeError("fixture_identity_or_start_changed")
    fixture=odds.match_event(e,[f for f in fixtures if f.get("league")==league],at)
    model=(fixture.get("markets") or {}).get("goals") if fixture else None
    if not isinstance(model,dict) or not odds.valid_probabilities(model.get("h2h")) or not runner.comparison_allowed(model,at):raise ProbeError("model_not_current_at_receipt")
    books=payload.get("bookmakerOdds")
    if not isinstance(books,dict):raise ProbeError("invalid_bookmaker_odds_schema")
    market_id,sides=definition;result={}
    for name in BOOKS:
        book=books.get(name)
        diag={"received":book is not None,"complete_active_markets":0,"model_matched_markets":0,
              "delivery_freshness_verified":False,"price_change_age_buckets":{},"rejection":None}
        result[name]=diag
        if not isinstance(book,dict):diag["rejection"]="absent_or_invalid_book";continue
        if book.get("bookmakerIsActive") is not True or book.get("suspended") is not False:diag["rejection"]="book_inactive_or_suspended";continue
        market=book.get("markets",{}).get(market_id) if isinstance(book.get("markets"),dict) else None
        if not isinstance(market,dict) or market.get("marketActive") is not True:diag["rejection"]="missing_or_inactive_full_time_1x2";continue
        outcomes=market.get("outcomes");prices=[];ages=Counter()
        if not isinstance(outcomes,dict) or set(outcomes)!=set(sides.values()):diag["rejection"]="incomplete_or_extra_outcomes";continue
        for ident in sides.values():
            row=outcomes[ident];players=row.get("players") if isinstance(row,dict) else None
            value=players.get("0") if isinstance(players,dict) and set(players)=={"0"} else None
            if not isinstance(value,dict) or value.get("active") is not True or value.get("playerName") is not None or value.get("mainLine") is not True or value.get("exchangeMeta") is not None:
                diag["rejection"]="selection_not_explicitly_active_main_standard";break
            if not odds.finite_number(value.get("price"),1.01,1000):diag["rejection"]="invalid_decimal_price";break
            changed=odds.dt(value.get("changedAt"))
            if not changed or changed>at:diag["rejection"]="missing_invalid_or_future_price_change_time";break
            age=(at-changed).total_seconds()
            ages["up_to_120s" if age<=120 else "120s_to_1h" if age<=3600 else "over_1h"]+=1
            prices.append(value["price"])
        if diag["rejection"]:continue
        if not .85<=sum(1/x for x in prices)<=1.5:diag["rejection"]="implausible_margin";continue
        diag.update(complete_active_markets=1,model_matched_markets=1,price_change_age_buckets=dict(ages))
    return result


def run(authenticated=False,league="Premier League",output=REPORT):
    leagues=list(TOURNAMENTS) if league=="All leagues" else [league]
    if any(x not in TOURNAMENTS for x in leagues):raise ValueError("Unsupported league")
    budget=2+2*len(leagues)
    report={"provider":"OddsPapi","checked_at":datetime.now(timezone.utc).isoformat(),"requested_leagues":leagues,
      "requested_books":list(BOOKS),"max_metered_requests":budget,"metered_requests_attempted":0,"unmetered_requests_attempted":0,
      "raw_odds_saved":False,"operator_prices_independently_verified":False,"delivery_freshness_verified":False,
      "verified_value":False,"value_blockers":odds.value_blockers(),"leagues":[],
      "timestamp_policy":"changedAt is a price-change timestamp, not last delivery or independent operator verification."}
    report["status"]="not_requested" if not authenticated else "needs_api_key"
    key=os.getenv("ODDSPAPI_API_KEY","").strip() if authenticated else ""
    last_request=None
    def request(path,params):
        nonlocal last_request
        if path=="/account":report["unmetered_requests_attempted"]+=1
        else:
            if report["metered_requests_attempted"]>=budget:raise ProbeError("request_budget_exhausted")
            report["metered_requests_attempted"]+=1
        if last_request is not None:time.sleep(max(0,1.05-(time.monotonic()-last_request)))
        data,error=fetch(path,params,key);last_request=time.monotonic()
        if error:
            report["failed_endpoint"]=path
            raise ProbeError(error)
        return data
    status=0 if not authenticated else 2
    if key:
        try:
            latest=json.loads((runner.OUT/"latest.json").read_text());now=datetime.now(timezone.utc)
            generated=odds.dt(latest.get("generated_at"))
            if not generated or not 0<=(now-generated).total_seconds()<=12*3600 or not isinstance(latest.get("fixtures"),list):raise ProbeError("stale_analysis")
            report["analysis_generated_at"]=generated.isoformat()
            report["account_before"]=account_summary(request("/account",{}))
            account=report["account_before"]
            if not account["soccer_included"] or not all(account["requested_books_included"].values()):raise ProbeError("requested_ro_books_not_in_account")
            if account["remaining"]<budget+10:raise ProbeError("quota_reserve_guard")
            catalog=verified_tournaments(request("/tournaments",{"sportId":10,"language":"en"}),leagues)
            report["tournament_catalog_checks"]=catalog
            definition=market_definition(request("/markets",{"language":"en"}))
            report["full_time_1x2_catalog_verified"]=True
            for name in leagues:
                row={"league":name,"status":"catalog_not_confirmed","received_at":None}
                report["leagues"].append(row)
                if not catalog[name]:continue
                at=datetime.now(timezone.utc)
                payload=request("/fixtures",{"tournamentId":TOURNAMENTS[name][0],"sportId":10,"statusId":0,"hasOdds":"true",
                  "bookmakers":",".join(BOOKS),"from":at.isoformat(),"to":(at+timedelta(days=9)).isoformat(),"language":"en"})
                selected,n=choose_fixture(payload,latest["fixtures"],name,datetime.now(timezone.utc))
                row["eligible_model_fixtures"]=n
                if selected is None:row["status"]="no_unambiguous_current_model_fixture";continue
                payload=request("/odds",{"fixtureId":selected["fixtureId"],"bookmakers":",".join(BOOKS),"oddsFormat":"decimal","language":"en","verbosity":3})
                received=datetime.now(timezone.utc);row["received_at"]=received.isoformat()
                row["books"]=assess(payload,selected,latest["fixtures"],name,definition,received)
                row["status"]="structural_markets_only_freshness_unverified"
            report["account_after"]=account_summary(request("/account",{}))
            complete=all(row.get("books") and all(d["complete_active_markets"] for d in row["books"].values()) for row in report["leagues"])
            report["status"]="diagnostic_only_freshness_unverified" if complete else "incomplete_quote_validation"
            if complete:status=0
        except ProbeError as exc:report.update(status="probe_blocked",reason=str(exc))
        except Exception as exc:report.update(status="internal_error",reason=type(exc).__name__)
    report["finished_at"]=datetime.now(timezone.utc).isoformat()
    output.parent.mkdir(parents=True,exist_ok=True)
    runner.write_json_atomic(output,report)
    print("ODDSPAPI_DIAGNOSTIC "+json.dumps(report,ensure_ascii=False,allow_nan=False))
    return status


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authenticated",action="store_true")
    parser.add_argument("--league",choices=["All leagues",*TOURNAMENTS],default=os.getenv("PROBE_LEAGUE","Premier League"))
    args=parser.parse_args()
    raise SystemExit(run(args.authenticated or os.getenv("AUTHENTICATED_PROBE")=="true",args.league))
