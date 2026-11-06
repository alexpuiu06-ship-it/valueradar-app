"""Synthetic documented OddsPapi schemas; never authenticates or reads a real key."""
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock,patch
from urllib.error import URLError

import oddspapi_probe as probe
import runner
from test_odds_safety import fixture

NOW=datetime(2026,11,6,17,tzinfo=timezone.utc)
SECRET="test-only-never-log"


def catalog():
    return [{"marketId":101,"marketLength":3,"sportId":10,"marketType":"1x2","period":"fulltime",
      "handicap":0,"playerProp":False,"outcomes":[{"outcomeId":101,"outcomeName":"1"},
      {"outcomeId":102,"outcomeName":"X"},{"outcomeId":103,"outcomeName":"2"}]}]


def account():
    return {"api_key":SECRET,"current_subscription_id":"private-test-only","subscriptions":[
      {"subscription_id":"private-test-only","is_active":True,"request_limit":250,"request_count":0,
       "sport_ids":[10],"bookmakers":dict.fromkeys(probe.BOOKS,{})}]}


def fixture_payload(league="Premier League"):
    f=fixture()
    return {"fixtureId":"fixture-test-"+str(probe.TOURNAMENTS[league][0]),"sportId":10,
      "tournamentId":probe.TOURNAMENTS[league][0],"participant1Id":1,"participant2Id":2,
      "participant1Name":f["home"],"participant2Name":f["away"],"statusId":0,"statusName":"Pre-Game",
      "hasOdds":True,"startTime":runner.fixture_kickoff(f).isoformat(),"trueStartTime":None,"trueEndTime":None}


def quotes(league="Premier League"):
    row=fixture_payload(league)
    outcomes={str(101+i):{"players":{"0":{"active":True,"price":price,"changedAt":(NOW-timedelta(days=3)).isoformat(),
      "mainLine":True,"playerName":None,"exchangeMeta":None}}} for i,price in enumerate((2,3.5,4))}
    row["bookmakerOdds"]={book:{"bookmakerIsActive":True,"suspended":False,
      "markets":{"101":{"marketActive":True,"outcomes":deepcopy(outcomes)}}} for book in probe.BOOKS}
    return row


class OddsPapiTests(unittest.TestCase):
    def assess(self,payload=None):
        return probe.assess(payload or quotes(),fixture_payload(),[fixture()],"Premier League",probe.market_definition(catalog()),NOW)

    def test_old_price_change_does_not_prove_staleness_or_delivery_freshness(self):
        result=self.assess()
        for row in result.values():
            self.assertEqual(row["complete_active_markets"],1)
            self.assertEqual(row["model_matched_markets"],1)
            self.assertEqual(row["price_change_age_buckets"],{"over_1h":3})
            self.assertFalse(row["delivery_freshness_verified"])
        self.assertNotIn('"price"',json.dumps(result))

    def test_catalog_rejects_wrong_period_line_prop_and_ambiguous_market(self):
        for field,value in (("period","firsthalf"),("handicap",.5),("playerProp",True),("marketLength",2),("marketType","totals")):
            data=catalog();data[0][field]=value
            with self.subTest(field=field),self.assertRaises(probe.ProbeError):probe.market_definition(data)
        with self.assertRaises(probe.ProbeError):probe.market_definition(catalog()*2)
        data=catalog();data[0]["outcomes"][2]["outcomeName"]="1"
        with self.assertRaises(probe.ProbeError):probe.market_definition(data)

    def test_account_only_copies_quota_and_target_entitlement_booleans(self):
        summary=probe.account_summary(account())
        self.assertEqual(summary["remaining"],250)
        self.assertTrue(all(summary["requested_books_included"].values()))
        self.assertNotIn(SECRET,json.dumps(summary))
        self.assertNotIn("private-test",json.dumps(summary))
        for field,value in (("request_count",True),("request_limit",None),("request_count",251)):
            data=account();data["subscriptions"][0][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(probe.ProbeError):probe.account_summary(data)

    def test_wrong_jurisdiction_does_not_substitute_for_exact_ro_books(self):
        payload=quotes();payload["bookmakerOdds"]={"superbet":payload["bookmakerOdds"]["superbet.ro"]}
        result=self.assess(payload)
        self.assertTrue(all(row["complete_active_markets"]==0 for row in result.values()))
        data=account();data["subscriptions"][0]["bookmakers"]={"superbet":{},"betano":{}}
        self.assertFalse(any(probe.account_summary(data)["requested_books_included"].values()))

    def test_structural_quotes_reject_suspension_incomplete_alternate_and_bad_price(self):
        for case in ("suspended","inactive","incomplete","extra_player","alternate","prop","exchange","nan","boolean","future_time"):
            data=quotes();book=data["bookmakerOdds"]["superbet.ro"]
            market=book["markets"]["101"];value=market["outcomes"]["101"]["players"]["0"]
            if case=="suspended":book["suspended"]=True
            if case=="inactive":market["marketActive"]=False
            if case=="incomplete":market["outcomes"].pop("103")
            if case=="extra_player":market["outcomes"]["101"]["players"]["5"]=deepcopy(value)
            if case=="alternate":value["mainLine"]=False
            if case=="prop":value["playerName"]="Test"
            if case=="exchange":value["exchangeMeta"]={"lay":True}
            if case=="nan":value["price"]=float("nan")
            if case=="boolean":value["price"]=True
            if case=="future_time":value["changedAt"]=(NOW+timedelta(seconds=1)).isoformat()
            with self.subTest(case=case):
                result=self.assess(data)
                self.assertEqual(result["superbet.ro"]["complete_active_markets"],0)
                self.assertEqual(result["betano.ro"]["complete_active_markets"],1)

    def test_received_event_must_still_match_selected_fixture_and_model(self):
        for field,value in (("statusId",1),("statusName","In-Play"),("trueStartTime",NOW.isoformat()),
                            ("fixtureId","other"),("participant1Id",500),("participant1Name","Other Club"),
                            ("startTime",NOW.isoformat())):
            data=quotes();data[field]=value
            with self.subTest(field=field),self.assertRaises(probe.ProbeError):self.assess(data)
        started=datetime.fromisoformat(fixture_payload()["startTime"])+timedelta(seconds=1)
        with self.assertRaises(probe.ProbeError):probe.assess(quotes(),fixture_payload(),[fixture()],"Premier League",probe.market_definition(catalog()),started)

    def test_duplicate_fixture_ids_canonical_events_and_wrong_kickoff_are_not_chosen(self):
        first=fixture_payload();duplicate=deepcopy(first);duplicate["fixtureId"]="other"
        for payload in ([first,first],[first,duplicate],[first,{**first,"statusName":"In-Play"}]):
            self.assertEqual(probe.choose_fixture(payload,[fixture()],"Premier League",NOW),(None,0))
        first["startTime"]=(datetime.fromisoformat(first["startTime"])+timedelta(minutes=20)).isoformat()
        self.assertEqual(probe.choose_fixture([first],[fixture()],"Premier League",NOW),(None,0))

    def test_catalog_requires_correct_country_and_unique_id(self):
        row={"tournamentId":17,"categorySlug":"england","tournamentSlug":"premier-league"}
        self.assertTrue(probe.verified_tournaments([row],["Premier League"])["Premier League"])
        self.assertFalse(probe.verified_tournaments([{**row,"categorySlug":"south-africa"}],["Premier League"])["Premier League"])
        self.assertFalse(probe.verified_tournaments([row,row],["Premier League"])["Premier League"])

    def run_probe(self,folder,league="All leagues",remaining=250,error=None):
        root=Path(folder);fixtures=[]
        for name in probe.TOURNAMENTS:
            row=fixture();row["league"]=name;fixtures.append(row)
        (root/"latest.json").write_text(json.dumps({"generated_at":NOW.isoformat(),"fixtures":fixtures}))
        def fetch(path,params,key):
            self.assertEqual(key,SECRET)
            if error:return None,error
            if path=="/account":
                data=account();data["subscriptions"][0]["request_count"]=250-remaining
            elif path=="/markets":data=catalog()
            elif path=="/tournaments":data=[{"tournamentId":ident,"categorySlug":cat,"tournamentSlug":slugs[0]} for ident,cat,slugs in probe.TOURNAMENTS.values()]
            elif path=="/fixtures":
                name=next(k for k,v in probe.TOURNAMENTS.items() if v[0]==params["tournamentId"]);data=[fixture_payload(name)]
            else:
                name=next(k for k in probe.TOURNAMENTS if fixture_payload(k)["fixtureId"]==params["fixtureId"]);data=quotes(name)
            return data,None
        stream=io.StringIO();clock=MagicMock();clock.now.return_value=NOW
        with patch.object(runner,"OUT",root),patch.object(probe,"datetime",clock),patch.dict("os.environ",{"ODDSPAPI_API_KEY":SECRET}),\
             patch.object(probe,"fetch",side_effect=fetch) as network,patch.object(probe.time,"sleep"),redirect_stdout(stream):
            code=probe.run(True,league,root/"report.json")
        return code,json.loads((root/"report.json").read_text()),stream.getvalue(),network

    def test_all_leagues_max_twelve_metered_requests_two_unmetered_and_no_raw_data(self):
        with tempfile.TemporaryDirectory() as folder:code,report,logged,network=self.run_probe(folder)
        self.assertEqual(code,0)
        self.assertEqual(report["metered_requests_attempted"],12)
        self.assertEqual(report["unmetered_requests_attempted"],2)
        self.assertEqual(network.call_count,14)
        self.assertEqual(len(report["leagues"]),5)
        self.assertFalse(report["delivery_freshness_verified"])
        self.assertFalse(report["verified_value"])
        for forbidden in (SECRET,"private-test",'"price"','"bookmakerOdds"','"api_key"','"participant1Name"'):
            self.assertNotIn(forbidden,json.dumps(report));self.assertNotIn(forbidden,logged)

    def test_one_league_is_four_metered_requests(self):
        with tempfile.TemporaryDirectory() as folder:code,report,_,_=self.run_probe(folder,"Premier League")
        self.assertEqual(code,0);self.assertEqual(report["metered_requests_attempted"],4)

    def test_low_quota_stops_before_any_metered_request(self):
        with tempfile.TemporaryDirectory() as folder:code,report,_,network=self.run_probe(folder,remaining=21)
        self.assertEqual(code,2);self.assertEqual(report["reason"],"quota_reserve_guard")
        self.assertEqual(report["metered_requests_attempted"],0);self.assertEqual(network.call_count,1)

    def test_missing_key_and_unauthenticated_modes_never_call_network(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(probe,"fetch") as network,\
             patch.dict("os.environ",{"ODDSPAPI_API_KEY":""}),redirect_stdout(io.StringIO()):
            output=Path(folder)/"report.json"
            self.assertEqual(probe.run(output=output),0)
            self.assertEqual(probe.run(authenticated=True,output=output),2)
        network.assert_not_called()

    def test_provider_error_is_bounded_without_retry(self):
        with tempfile.TemporaryDirectory() as folder:code,report,_,network=self.run_probe(folder,error="http_401")
        self.assertEqual(code,2);self.assertEqual(network.call_count,1)
        self.assertEqual(report["reason"],"http_401")

    def test_fetch_hides_query_credentials_and_exception_text_and_rejects_redirects(self):
        opener=MagicMock();opener.open.side_effect=URLError("https://test.invalid/?apiKey="+SECRET)
        with patch.object(probe.urllib.request,"build_opener",return_value=opener):
            data,error=probe.fetch("/account",{},SECRET)
        self.assertIsNone(data);self.assertEqual(error,"URLError")
        self.assertNotIn(SECRET,error)
        with self.assertRaises(ValueError):probe.NoRedirect().redirect_request(None,None,None,None,None,None)

    def test_global_catalog_has_a_larger_explicit_bound_than_odds_payloads(self):
        response=MagicMock();response.__enter__.return_value=response
        response.read.return_value=json.dumps(catalog()).encode()+b" "*5000001
        opener=MagicMock();opener.open.return_value=response
        with patch.object(probe.urllib.request,"build_opener",return_value=opener):
            data,error=probe.fetch("/markets",{},SECRET)
            self.assertIsNone(error);self.assertEqual(data,catalog())
            response.read.assert_called_with(32*1024*1024+1)
            data,error=probe.fetch("/odds",{},SECRET)
            self.assertIsNone(data);self.assertEqual(error,"response_size_limit")


if __name__=="__main__":unittest.main()
