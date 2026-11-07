"""Exercise safe Git publication, immutable journals and recovery authorization."""
from contextlib import chdir
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import publish_generated, recover_pages, validate_outputs, verify_live_site


def git(folder, *args):
    return subprocess.run(["git", "-C", str(folder), *args], check=True,
                          text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.strip()


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.remote = self.root / "origin.git"
        subprocess.run(["git", "init", "--bare", "--initial-branch=main", str(self.remote)],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.local = self.root / "local"
        subprocess.run(["git", "clone", str(self.remote), str(self.local)],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        git(self.local, "config", "user.name", "test")
        git(self.local, "config", "user.email", "test@example.invalid")
        (self.local / "docs").mkdir()
        for name in ("model_lab.json", "calibration_report.json", "elo_challenger.json"):
            (self.local / "docs" / name).write_text("{}\n")
        (self.local / "code.py").write_text("unchanged = True\n")
        git(self.local, "add", ".")
        git(self.local, "commit", "-m", "initial")
        git(self.local, "push", "origin", "main")
        self.sha = git(self.local, "rev-parse", "HEAD")

    def test_saves_only_owned_reports_without_resetting_code(self):
        (self.local / "docs/model_lab.json").write_text('{"n":42}\n')
        with chdir(self.local):
            saved = publish_generated.publish("lab", self.sha)
        self.assertEqual(saved, git(self.remote, "rev-parse", "main"))
        self.assertEqual("docs/model_lab.json", git(self.local, "diff-tree", "--no-commit-id", "--name-only", "-r", saved))
        self.assertEqual("unchanged = True\n", (self.local / "code.py").read_text())

    def test_new_main_commit_aborts_instead_of_overwriting_forecasts(self):
        other = self.root / "other"
        subprocess.run(["git", "clone", str(self.remote), str(other)],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        git(other, "config", "user.name", "other")
        git(other, "config", "user.email", "other@example.invalid")
        (other / "docs/model_lab.json").write_text('{"newer":true}\n')
        git(other, "add", ".")
        git(other, "commit", "-m", "newer data")
        git(other, "push", "origin", "main")
        advanced = git(other, "rev-parse", "HEAD")
        (self.local / "docs/model_lab.json").write_text('{"stale":true}\n')
        with chdir(self.local), self.assertRaisesRegex(RuntimeError, "main advanced"):
            publish_generated.publish("lab", self.sha)
        self.assertEqual(advanced, git(self.remote, "rev-parse", "main"))
        self.assertEqual(self.sha, git(self.local, "rev-parse", "HEAD"))
        self.assertIn("stale", (self.local / "docs/model_lab.json").read_text())

    def test_unowned_or_staged_changes_are_never_published(self):
        (self.local / "docs/elo_challenger.json").write_text('{"unowned":true}\n')
        with chdir(self.local), self.assertRaisesRegex(RuntimeError, "outside the output allowlist"):
            publish_generated.publish("lab", self.sha)
        self.assertEqual(self.sha, git(self.remote, "rev-parse", "main"))
        git(self.local, "add", ".")
        with chdir(self.local), self.assertRaisesRegex(RuntimeError, "staged changes"):
            publish_generated.publish("lab", self.sha)


class OutputContractTests(unittest.TestCase):
    def test_frozen_fields_and_records_cannot_be_rewritten_or_dropped(self):
        original = [{"league": "Ligue 1", "date": "2026-01-01", "home": "A", "away": "B",
                     "market": "h2h", "probabilities": {"home": .5, "draw": .3, "away": .2}, "settled": False}]
        settled = {**original[0], "settled": True, "actual_outcome": "home"}
        validate_outputs.validate_log([settled], original)
        with self.assertRaisesRegex(ValueError, "removed"):
            validate_outputs.validate_log([], original)
        with self.assertRaisesRegex(ValueError, "rewritten"):
            validate_outputs.validate_log([{**settled, "probabilities": {"home": 1}}], original)

    def test_new_forecasts_require_pre_kickoff_evidence(self):
        record = {"league": "Ligue 1", "date": "2026-01-01", "home": "A", "away": "B",
                  "market": "h2h", "created_at": "2026-01-01T12:00:00Z", "kickoff_utc": "2026-01-01T12:00:00Z"}
        with self.assertRaisesRegex(ValueError, "before kickoff"):
            validate_outputs.validate_log([record], [])
        record["created_at"] = "2026-01-01T11:00:00Z"
        validate_outputs.validate_log([record], [])

    def test_pipeline_versions_are_separate_immutable_forecasts(self):
        legacy = {"league": "Ligue 1", "date": "2026-01-01", "home": "A", "away": "B",
                  "market": "h2h", "created_at": "2025-12-31T12:00:00Z", "settled": False}
        new = {**legacy, "pipeline_version": "validated_identity_v2", "kickoff_utc": "2026-01-01T12:00:00Z"}
        validate_outputs.validate_log([legacy, new], [legacy])

    def test_spoofed_watchlist_cannot_pass_contracts(self):
        watch = {"items": [], "live_ro_supported": False}
        audit = {"initial_positive_ev_signals": 0, "signals_settled": 0, "hypothetical_roi": None,
                 "model_is_verified": False, "quotes_are_verified_romania": False}
        validate_outputs.validate_safety(watch, audit)
        with self.assertRaisesRegex(ValueError, "never enter"):
            validate_outputs.validate_safety({**watch, "items": [{"verified": True}]}, audit)
        with self.assertRaisesRegex(ValueError, "profit claim"):
            validate_outputs.validate_safety(watch, {**audit, "hypothetical_roi": .4})


class PagesRecoveryTests(unittest.TestCase):
    def request_result(self, status):
        class Response:
            def __init__(self, data, code=200):
                self.data, self.status = data, code

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self):
                return json.dumps(self.data).encode()
        return [Response({"status": status}), Response({}, 204)]

    def test_only_explicit_pending_deployment_can_be_cancelled(self):
        env = {"DEPLOYMENT_ID": "a" * 40, "GITHUB_REPOSITORY": "owner/repo", "GH_TOKEN": "test-only"}
        with patch.dict("os.environ", env, clear=True), patch("urllib.request.urlopen", side_effect=self.request_result("deployment_in_progress")) as network:
            recover_pages.main()
        self.assertEqual(network.call_args_list[1].args[0].get_method(), "POST")
        self.assertTrue(network.call_args_list[1].args[0].full_url.endswith("/" + "a" * 40 + "/cancel"))
        with patch.dict("os.environ", env, clear=True), patch("urllib.request.urlopen", side_effect=self.request_result("succeed")) as network:
            with self.assertRaisesRegex(SystemExit, "refused"):
                recover_pages.main()
            self.assertEqual(network.call_count, 1)

    def test_path_injection_rejected_before_any_request(self):
        with patch.dict("os.environ", {"DEPLOYMENT_ID": "../other/cancel"}, clear=True), patch("urllib.request.urlopen") as network:
            with self.assertRaises(SystemExit):
                recover_pages.main()
            network.assert_not_called()


class PublicDeploymentTests(unittest.TestCase):
    def test_delayed_snapshot_can_propagate_but_a_persistently_old_snapshot_fails(self):
        class Response:
            def __init__(self,stamp):self.stamp=stamp
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self):return json.dumps({"generated_at":self.stamp}).encode()
        with patch.object(verify_live_site.urllib.request,"urlopen",side_effect=[Response("old"),Response("old"),Response("new")]) as network,patch.object(verify_live_site.time,"sleep"):
            verify_live_site.verify("https://owner.github.io/repo/","new",attempts=3)
            self.assertEqual(network.call_count,3)
        with patch.object(verify_live_site.urllib.request,"urlopen",side_effect=lambda *args,**kwargs:Response("old")) as network,patch.object(verify_live_site.time,"sleep"):
            with self.assertRaises(RuntimeError):verify_live_site.verify("https://owner.github.io/repo/","new",attempts=3)
            self.assertEqual(network.call_count,3)

    def test_http_success_with_old_data_cannot_verify_deployment(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self):
                return b'{"generated_at":"old"}'
        with patch("urllib.request.urlopen", return_value=Response()):
            with self.assertRaisesRegex(RuntimeError, "could not be verified"):
                verify_live_site.verify("https://owner.github.io/repo/", "new", attempts=1)
            verify_live_site.verify("https://owner.github.io/repo/", "old", attempts=1)


if __name__ == "__main__":
    unittest.main()
