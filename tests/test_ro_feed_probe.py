"""Documented PropLine schema, synthetic tests only; no authenticated API calls."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,MagicMock
from urllib.error import URLError

import ro_feed_probe as probe
import runner
from test_odds_safety import fixture,event

NOW=datetime(2026,11,6,17,tzinfo=timezone.utc)


def response():
    e=event()
    e.update(live=False,is_outright=False)
    template=e["bookmakers"][0]
    template["markets"][0]["last_update"]=(NOW-timedelta(seconds=20)).isoformat()
    for row,price in zip(template["markets"][0]["outcomes"],(-110,300,275)):
        row["price"]=price
        row["last_seen_at"]=(NOW-timedelta(seconds=10)).isoformat()
    e["bookmakers"]=[{**deepcopy(template),"key":book} for book in probe.BOOKS]
    return e


class ProbeTests(unittest.TestCase):
    def test_american_conversion_is_explicit_and_never_guesses_decimal(self):
        self.assertAlmostEqual(probe.american_decimal(-200),1.5)
        self.assertAlmostEqual(probe.american_decimal(250),3.5)
        for value in (None,True,1.95,0,-1,99,100.5,float("nan"),float("inf"),"200"):
            with self.assertRaises(ValueError):probe.american_decimal(value)

    def test_both_explicit_ro_books_can_be_assessed_without_saving_quotes(self):
        summary=probe.assess([response()],[fixture()],"Premier League",NOW)
        self.assertEqual(summary["matched_current_model_markets"],dict.fromkeys(probe.BOOKS,1))
        self.assertFalse(summary["raw_odds_saved"])
        self.assertFalse(summary["verified_value"])
        self.assertNotIn("odds",summary)

    def test_wrong_region_and_generic_book_labels_are_not_substitutes(self):
        e=response();e["bookmakers"][0]["key"]="superbet";e["bookmakers"][1]["key"]="netbet"
        self.assertEqual(probe.assess([e],[fixture()],"Premier League",NOW)["complete_recent_markets"],{})

    def test_live_started_or_outright_event_is_rejected(self):
        for changed in ({"live":True},{"is_outright":True},{"commence_time":NOW.isoformat()}):
            self.assertEqual(probe.assess([{**response(),**changed}],[fixture()],"Premier League",NOW)["complete_recent_markets"],{})

    def test_half_markets_suspensions_and_stale_deliveries_are_rejected(self):
        for changes in ({"period":"h1"},{"suspended_at":NOW.isoformat()},{"last_update":(NOW-timedelta(minutes=3)).isoformat()}):
            e=response()
            for book in e["bookmakers"]:book["markets"][0].update(changes)
            self.assertEqual(probe.assess([e],[fixture()],"Premier League",NOW)["complete_recent_markets"],{})

    def test_missing_selection_delivery_and_incomplete_market_are_rejected(self):
        for count in (2,3):
            e=response()
            for book in e["bookmakers"]:
                book["markets"][0]["outcomes"]=book["markets"][0]["outcomes"][:count]
                book["markets"][0]["outcomes"][0].pop("last_seen_at")
            self.assertEqual(probe.assess([e],[fixture()],"Premier League",NOW)["complete_recent_markets"],{})

    def test_event_identity_does_not_fuzzy_match_or_ignore_kickoff(self):
        for change in ({"home_team":"Arsenall"},{"commence_time":"2026-11-07T16:00:00Z"}):
            result=probe.assess([{**response(),**change}],[fixture()],"Premier League",NOW)
            self.assertEqual(result["matched_current_model_markets"],{})

    def test_stale_model_is_not_counted_as_matched_even_with_valid_prices(self):
        f=fixture();f["markets"]["goals"]["availability"]={"comparison_allowed":False}
        result=probe.assess([response()],[f],"Premier League",NOW)
        self.assertTrue(result["complete_recent_markets"])
        self.assertEqual(result["matched_current_model_markets"],{})

    def test_duplicate_provider_identity_is_quarantined_in_full(self):
        e=response()
        self.assertEqual(probe.assess([e,deepcopy(e)],[fixture()],"Premier League",NOW)["complete_recent_markets"],{})

    def test_malformed_provider_shapes_are_not_valid_prices(self):
        for data in (None,{},{"events":[]}):
            with self.assertRaises(ValueError):probe.assess(data,[],"Premier League",NOW)
        for e in (None,{},{"id":[]},response()|{"bookmakers":[{"key":[]}]}):
            self.assertEqual(probe.assess([e],[],"Premier League",NOW)["complete_recent_markets"],{})

    def test_public_health_is_never_quote_validation(self):
        result=probe.summarize_health({"as_of":NOW.isoformat(),"bookmakers":[{"key":"superbet_ro","is_stale":False}]})
        self.assertTrue(result["books"][0]["present"])
        self.assertFalse(result["books"][1]["present"])
        self.assertIn("individual",result["books"][0]["warning"])

    def test_missing_key_makes_no_request_and_writes_actionable_status(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict("os.environ",{"PROPLINE_API_KEY":""}),patch.object(probe,"fetch") as network:
            output=Path(folder)/"report.json"
            self.assertEqual(probe.run(authenticated=True,output=output),2)
            network.assert_not_called()
            report=json.loads(output.read_text())
            self.assertEqual(report["status"],"needs_api_key")
            self.assertFalse(report["verified_value"])

    def test_network_error_does_not_expose_key_and_redirect_cannot_forward_it(self):
        secret="TEST_ONLY_DO_NOT_LEAK"
        opener=MagicMock()
        opener.open.side_effect=URLError("provider echoed "+secret)
        with patch("urllib.request.build_opener",return_value=opener):
            payload,headers,error=probe.fetch("/freshness",secret)
        self.assertNotIn(secret,str((payload,headers,error)))
        request=opener.open.call_args.args[0]
        self.assertNotIn(secret,request.full_url)
        self.assertEqual(request.get_header("X-api-key"),secret)
        with self.assertRaises(ValueError):probe.NoRedirect().redirect_request()


if __name__=="__main__":unittest.main()
