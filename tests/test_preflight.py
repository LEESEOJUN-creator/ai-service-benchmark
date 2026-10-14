import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from benchmark.measurements import credit_delta
from benchmark.planning import build_plan, project_path


ROOT = Path(__file__).resolve().parents[1]


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for folder in ("config", "sites", "cases", "fixtures"):
            shutil.copytree(ROOT / folder, self.root / folder)

    def read(self, path):
        return json.loads((self.root / path).read_text(encoding="utf-8"))

    def write(self, path, data):
        (self.root / path).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def configured(self):
        # Synthetic test profiles only; these do NOT certify any real service.
        config = self.read("config/benchmark.json")
        config["budget_krw_per_service"] = "100"
        self.write("config/benchmark.json", config)
        for service in config["services"]:
            path = "sites/" + service + ".json"
            profile = self.read(path)
            profile.update(url="https://example.invalid", browser_flow_verified=True,
                           capabilities=["text", "image_upload", "pdf_upload"])
            profile["credit_observation"]["status"] = "verified"
            profile["models"]["gemini-candidate"] = {
                "verified": True, "canonical_model": "synthetic-model", "version": "test-1",
                "reasoning": {"mode": "fixed", "level": "low", "budget_tokens": None},
                "feature_settings": {"web_search": False, "memory": False},
                "evidence_scope": "ui_declared", "evidence": "synthetic test fixture",
                "max_request_cost_krw": "2"
            }
            self.write(path, profile)

    def test_default_blocks_and_counts_followups(self):
        plan = build_plan(self.root)
        self.assertEqual(plan["status"], "blocked")
        self.assertEqual(plan["requests_planned"], 9)
        self.assertFalse(plan["live_execution_implemented"])
        self.assertIsNone(plan["planned_cost_upper_bound_krw"]["monogpt"])

    def test_matching_conditions_allow_only_offline_readiness(self):
        self.configured()
        plan = build_plan(self.root)
        self.assertEqual(plan["status"], "ready_for_implementation")
        self.assertFalse(plan["live_execution_implemented"])
        self.assertEqual(plan["planned_cost_upper_bound_krw"]["monogpt"], "6")
        self.assertTrue(any("백엔드" in warning for warning in plan["warnings"]))

    def test_model_reasoning_and_features_mismatch_block(self):
        self.configured()
        path = "sites/timely.json"
        original = self.read(path)
        variants = {
            "version": "test-2",
            "reasoning": {"mode": "fixed", "level": "high", "budget_tokens": None},
            "feature_settings": {"web_search": True, "memory": False}
        }
        for field, value in variants.items():
            with self.subTest(field=field):
                changed = json.loads(json.dumps(original))
                changed["models"]["gemini-candidate"][field] = value
                self.write(path, changed)
                self.assertTrue(any("불일치" in b for b in build_plan(self.root)["blockers"]))

    def test_unknown_reasoning_and_missing_model_do_not_fallback(self):
        self.configured()
        path = "sites/timely.json"
        profile = self.read(path)
        profile["models"]["gemini-candidate"]["reasoning"]["level"] = "unknown"
        self.write(path, profile)
        self.assertEqual(build_plan(self.root)["status"], "blocked")
        profile["models"] = {}
        self.write(path, profile)
        self.assertFalse(build_plan(self.root)["comparison_groups"][0]["conditions_match"])

    def test_request_and_budget_caps(self):
        self.configured()
        config = self.read("config/benchmark.json")
        config.update(max_total_requests=8, budget_krw_per_service="5")
        self.write("config/benchmark.json", config)
        blockers = build_plan(self.root)["blockers"]
        self.assertTrue(any("총 요청" in b for b in blockers))
        self.assertTrue(any("예산 초과" in b for b in blockers))

    def test_prompt_change_changes_input_hash(self):
        before = build_plan(self.root)["inputs"][0]["input_sha256"]
        cases = self.read("cases/smoke.json")
        cases["cases"][0]["turns"][0] += " "
        self.write("cases/smoke.json", cases)
        self.assertNotEqual(before, build_plan(self.root)["inputs"][0]["input_sha256"])

    def test_missing_review_personal_file_and_changed_bytes_block(self):
        self.configured()
        fixture_path = self.root / "fixtures" / "sample.bin"
        fixture_path.write_bytes(b"synthetic non-personal test bytes")
        fixture = {"id": "public-table-image", "path": "fixtures/sample.bin",
                   "sha256": hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
                   "classification": "public", "review_status": "approved",
                   "review_note": "synthetic bytes", "allowed_services": ["monogpt", "timely", "works-ai"]}
        self.write("fixtures/manifest.json", {"schema_version": 1, "fixtures": [fixture]})
        cases = self.read("cases/smoke.json")
        cases["cases"][2].update(enabled=True, expected={"synthetic": True})
        self.write("cases/smoke.json", cases)
        self.assertEqual(build_plan(self.root)["status"], "ready_for_implementation")
        for field, value in [("classification", "personal"), ("review_status", "pending"),
                             ("allowed_services", ["monogpt"])]:
            with self.subTest(field=field):
                changed = dict(fixture, **{field: value})
                self.write("fixtures/manifest.json", {"schema_version": 1, "fixtures": [changed]})
                self.assertEqual(build_plan(self.root)["status"], "blocked")
        self.write("fixtures/manifest.json", {"schema_version": 1, "fixtures": [fixture]})
        fixture_path.write_bytes(b"changed")
        self.assertTrue(any("해시 불일치" in b for b in build_plan(self.root)["blockers"]))

    def test_path_escape_and_symlink_escape_rejected(self):
        with self.assertRaises(ValueError):
            project_path(self.root, "../outside")
        (self.root / "external").symlink_to(self.root.parent, target_is_directory=True)
        with self.assertRaises(ValueError):
            project_path(self.root, "external/outside")

    def test_duplicate_ids_rejected(self):
        cases = self.read("cases/smoke.json")
        cases["cases"].append(cases["cases"][0])
        self.write("cases/smoke.json", cases)
        with self.assertRaises(ValueError):
            build_plan(self.root)


class MeasurementTests(unittest.TestCase):
    def test_exact_decimal_arithmetic(self):
        self.assertEqual(credit_delta("12500", "12380", settled=True)["consumed"], "120")
        self.assertEqual(credit_delta("1.30", "1.10", settled=True, display_step="0.01")["consumed"], "0.20")

    def test_pending_contaminated_or_missing_is_not_zero(self):
        examples = [
            credit_delta("100", "90", settled=False),
            credit_delta("100", "110", settled=True),
            credit_delta("100", "90", settled=True, concurrent_activity=True),
            credit_delta(None, "90", settled=True),
            credit_delta("100", "100", settled=True)
        ]
        for measurement in examples:
            self.assertIsNone(measurement["consumed"])

    def test_invalid_numeric_values_rejected(self):
        for value in ["NaN", "Infinity", "-1", "1,000 크레딧"]:
            with self.subTest(value=value):
                self.assertEqual(credit_delta(value, "0", settled=True)["status"], "invalid_reading")


if __name__ == "__main__":
    unittest.main()
