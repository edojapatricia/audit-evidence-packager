"""
Audit Evidence Packager — edge-case test suite.

Mocks the Anthropic client so no real API key is needed.
Run:  python test_app.py
"""
import json
import sys
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

# ── Fake SSE stream helper ────────────────────────────────────────────────────
GOOD_MAPPING = {
    "summary": "This access-control policy addresses identity and authentication controls.",
    "mappings": [
        {
            "framework": "ISO 27001",
            "control_id": "A.5.15",
            "control_name": "Access control",
            "coverage": "Full",
            "rationale": "Policy explicitly defines access-control rules and enforcement.",
            "gaps": "",
        },
        {
            "framework": "ISO 27001",
            "control_id": "A.5.16",
            "control_name": "Identity management",
            "coverage": "Partial",
            "rationale": "Identity lifecycle is mentioned but provisioning details are thin.",
            "gaps": "Add provisioning/deprovisioning workflow documentation.",
        },
        {
            "framework": "SOC 2",
            "control_id": "CC6.1",
            "control_name": "Logical access security",
            "coverage": "Full",
            "rationale": "MFA and role-based access are documented.",
            "gaps": "",
        },
        {
            "framework": "SOC 2",
            "control_id": "CC6.3",
            "control_name": "Role-based access and least privilege",
            "coverage": "Insufficient",
            "rationale": "Policy references roles but no RBAC matrix is attached.",
            "gaps": "Attach or reference the RBAC matrix and privilege-review schedule.",
        },
    ],
    "overall_coverage": {
        "iso_27001_controls": ["A.5.15", "A.5.16"],
        "soc2_criteria": ["CC6.1", "CC6.3"],
        "risk_level": "Medium",
        "recommendations": [
            "Attach the RBAC matrix.",
            "Document provisioning/deprovisioning workflow.",
            "Include periodic access-review cadence.",
        ],
    },
}


def _make_mock_stream(text: str):
    """Return a mock context-manager that yields text one char at a time."""
    mock_stream = MagicMock()
    mock_stream.__enter__ = MagicMock(return_value=mock_stream)
    mock_stream.__exit__ = MagicMock(return_value=False)
    mock_stream.text_stream = iter(text)
    return mock_stream


def _read_sse(response) -> str:
    """Collect all text chunks from an SSE response into a single string."""
    full = ""
    raw = response.data  # Flask test client buffers the full response in .data
    for line in raw.split(b"\n"):
        line = line.decode("utf-8", errors="replace").strip()
        if not line.startswith("data: "):
            continue
        data = json.loads(line[6:])
        if data.get("type") == "text":
            full += data["content"]
    return full


def _iter_sse_events(response):
    """Yield parsed SSE event dicts from a buffered Flask test response."""
    for line in response.data.split(b"\n"):
        line = line.decode("utf-8", errors="replace").strip()
        if line.startswith("data: "):
            yield json.loads(line[6:])


# ── Test cases ────────────────────────────────────────────────────────────────
class TestAnalyzeEndpoint(unittest.TestCase):

    def setUp(self):
        os_env_patcher = patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test-dummy"})
        os_env_patcher.start()
        self.addCleanup(os_env_patcher.stop)

        import app as app_module
        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()
        self.app_module = app_module

    # ── Happy path ──────────────────────────────────────────────────────────

    def test_analyze_happy_path(self):
        """Well-formed evidence returns structured JSON with mappings."""
        payload = json.dumps(GOOD_MAPPING)
        mock_stream = _make_mock_stream(payload)
        with patch.object(self.app_module.client.messages, "stream", return_value=mock_stream):
            r = self.client.post(
                "/api/analyze",
                json={
                    "evidence_name": "Access Control Policy v3",
                    "evidence_text": "All users must authenticate with MFA. Role-based access is enforced.",
                    "frameworks": ["ISO 27001", "SOC 2"],
                },
            )
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/event-stream", r.content_type)
        full = _read_sse(r)
        self.assertIn("mappings", full)
        self.assertIn("overall_coverage", full)

    def test_analyze_iso_only(self):
        """Single-framework request works and streams correctly."""
        iso_only = dict(GOOD_MAPPING)
        iso_only["mappings"] = [m for m in GOOD_MAPPING["mappings"] if m["framework"] == "ISO 27001"]
        mock_stream = _make_mock_stream(json.dumps(iso_only))
        with patch.object(self.app_module.client.messages, "stream", return_value=mock_stream):
            r = self.client.post(
                "/api/analyze",
                json={
                    "evidence_name": "Encryption Standard",
                    "evidence_text": "AES-256 is mandated for all data at rest.",
                    "frameworks": ["ISO 27001"],
                },
            )
        self.assertEqual(r.status_code, 200)

    def test_analyze_soc2_only(self):
        """SOC 2-only request streams correctly."""
        soc_only = dict(GOOD_MAPPING)
        soc_only["mappings"] = [m for m in GOOD_MAPPING["mappings"] if m["framework"] == "SOC 2"]
        mock_stream = _make_mock_stream(json.dumps(soc_only))
        with patch.object(self.app_module.client.messages, "stream", return_value=mock_stream):
            r = self.client.post(
                "/api/analyze",
                json={
                    "evidence_name": "Availability SLA",
                    "evidence_text": "System uptime guaranteed at 99.9% per SLA.",
                    "frameworks": ["SOC 2"],
                },
            )
        self.assertEqual(r.status_code, 200)

    # ── Input validation ────────────────────────────────────────────────────

    def test_analyze_empty_evidence_text(self):
        """Empty evidence_text must return 400."""
        r = self.client.post("/api/analyze", json={"evidence_name": "Test", "evidence_text": "", "frameworks": ["ISO 27001"]})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_analyze_whitespace_only_evidence(self):
        """Whitespace-only evidence_text must return 400."""
        r = self.client.post("/api/analyze", json={"evidence_name": "Test", "evidence_text": "   \n\t  ", "frameworks": ["ISO 27001"]})
        self.assertEqual(r.status_code, 400)

    def test_analyze_missing_evidence_text_key(self):
        """Missing evidence_text key should return 400 (defaults to empty string)."""
        r = self.client.post("/api/analyze", json={"evidence_name": "No text key"})
        self.assertEqual(r.status_code, 400)

    def test_analyze_empty_body(self):
        """Completely empty JSON body must return 400."""
        r = self.client.post("/api/analyze", json={})
        self.assertEqual(r.status_code, 400)

    def test_analyze_no_frameworks_defaults(self):
        """Missing frameworks key should default — not crash — and still call Claude."""
        mock_stream = _make_mock_stream(json.dumps(GOOD_MAPPING))
        with patch.object(self.app_module.client.messages, "stream", return_value=mock_stream):
            r = self.client.post(
                "/api/analyze",
                json={"evidence_text": "Some policy text here."},
            )
        self.assertEqual(r.status_code, 200)

    def test_analyze_empty_frameworks_list(self):
        """Empty frameworks list should still produce a 200 (defaults applied server-side)."""
        mock_stream = _make_mock_stream(json.dumps(GOOD_MAPPING))
        with patch.object(self.app_module.client.messages, "stream", return_value=mock_stream):
            r = self.client.post(
                "/api/analyze",
                json={"evidence_text": "Some policy text.", "frameworks": []},
            )
        self.assertEqual(r.status_code, 200)

    # ── Content edge cases ──────────────────────────────────────────────────

    def test_analyze_very_long_evidence(self):
        """Evidence text with 50 000 chars should stream without truncation."""
        long_text = "A" * 50_000
        mock_stream = _make_mock_stream(json.dumps(GOOD_MAPPING))
        with patch.object(self.app_module.client.messages, "stream", return_value=mock_stream):
            r = self.client.post(
                "/api/analyze",
                json={"evidence_text": long_text, "frameworks": ["ISO 27001"]},
            )
        self.assertEqual(r.status_code, 200)

    def test_analyze_irrelevant_content(self):
        """Non-compliance content (recipe) should still return 200 — Claude decides relevance."""
        mock_stream = _make_mock_stream(json.dumps(GOOD_MAPPING))
        with patch.object(self.app_module.client.messages, "stream", return_value=mock_stream):
            r = self.client.post(
                "/api/analyze",
                json={
                    "evidence_text": "Ingredients: 2 cups flour, 1 egg, 200ml milk. Mix well and bake at 180°C.",
                    "frameworks": ["ISO 27001", "SOC 2"],
                },
            )
        self.assertEqual(r.status_code, 200)

    def test_analyze_unicode_and_emoji(self):
        """Unicode text with emoji and CJK characters must not crash."""
        text = "ポリシー: 全ユーザーはMFA必須 🔐 Access must be logged ✅ 审计日志保留180天"
        mock_stream = _make_mock_stream(json.dumps(GOOD_MAPPING))
        with patch.object(self.app_module.client.messages, "stream", return_value=mock_stream):
            r = self.client.post("/api/analyze", json={"evidence_text": text, "frameworks": ["ISO 27001"]})
        self.assertEqual(r.status_code, 200)

    def test_analyze_xss_in_evidence_name(self):
        """XSS payload in evidence_name must not cause a server error."""
        xss = '<script>alert("xss")</script>'
        mock_stream = _make_mock_stream(json.dumps(GOOD_MAPPING))
        with patch.object(self.app_module.client.messages, "stream", return_value=mock_stream):
            r = self.client.post(
                "/api/analyze",
                json={"evidence_name": xss, "evidence_text": "Some valid policy text.", "frameworks": ["ISO 27001"]},
            )
        self.assertEqual(r.status_code, 200)

    def test_analyze_json_in_evidence_text(self):
        """Evidence that is itself JSON (e.g. a config export) should not confuse the parser."""
        config_json = json.dumps({"mfa_enabled": True, "session_timeout": 900, "roles": ["admin", "viewer"]})
        mock_stream = _make_mock_stream(json.dumps(GOOD_MAPPING))
        with patch.object(self.app_module.client.messages, "stream", return_value=mock_stream):
            r = self.client.post(
                "/api/analyze",
                json={"evidence_text": config_json, "frameworks": ["SOC 2"]},
            )
        self.assertEqual(r.status_code, 200)

    def test_analyze_special_characters(self):
        """Evidence with SQL/shell injection characters must not crash."""
        evil = "'; DROP TABLE controls; --  && rm -rf / | cat /etc/passwd"
        mock_stream = _make_mock_stream(json.dumps(GOOD_MAPPING))
        with patch.object(self.app_module.client.messages, "stream", return_value=mock_stream):
            r = self.client.post("/api/analyze", json={"evidence_text": evil, "frameworks": ["ISO 27001"]})
        self.assertEqual(r.status_code, 200)

    def test_analyze_binary_looking_text(self):
        """Null bytes and control characters in evidence text must not crash the server."""
        binary_text = "Policy\x00Version\x01\x02\x03: Access control enforced."
        mock_stream = _make_mock_stream(json.dumps(GOOD_MAPPING))
        with patch.object(self.app_module.client.messages, "stream", return_value=mock_stream):
            r = self.client.post("/api/analyze", json={"evidence_text": binary_text, "frameworks": ["ISO 27001"]})
        self.assertEqual(r.status_code, 200)

    def test_analyze_evidence_name_missing_defaults_gracefully(self):
        """Missing evidence_name should default to 'Unnamed Evidence', not crash."""
        mock_stream = _make_mock_stream(json.dumps(GOOD_MAPPING))
        with patch.object(self.app_module.client.messages, "stream", return_value=mock_stream):
            r = self.client.post("/api/analyze", json={"evidence_text": "Valid policy text."})
        self.assertEqual(r.status_code, 200)

    def test_analyze_wrong_content_type(self):
        """Non-JSON content-type should return 400 or 415, not 500."""
        r = self.client.post(
            "/api/analyze",
            data="evidence_text=hello",
            content_type="application/x-www-form-urlencoded",
        )
        self.assertIn(r.status_code, [400, 415, 500])

    # ── SSE stream format ───────────────────────────────────────────────────

    def test_sse_events_are_well_formed(self):
        """Every SSE event must contain valid JSON with a known type."""
        mock_stream = _make_mock_stream(json.dumps(GOOD_MAPPING))
        with patch.object(self.app_module.client.messages, "stream", return_value=mock_stream):
            r = self.client.post(
                "/api/analyze",
                json={"evidence_text": "Valid policy.", "frameworks": ["ISO 27001"]},
            )
        events = list(_iter_sse_events(r))
        self.assertGreater(len(events), 0, "No SSE events received")
        for ev in events:
            self.assertIn(ev.get("type"), ["text", "done"], f"Unknown event type: {ev}")

    def test_sse_ends_with_done_event(self):
        """Stream must terminate with a type='done' event."""
        mock_stream = _make_mock_stream(json.dumps(GOOD_MAPPING))
        with patch.object(self.app_module.client.messages, "stream", return_value=mock_stream):
            r = self.client.post(
                "/api/analyze",
                json={"evidence_text": "Some text.", "frameworks": ["SOC 2"]},
            )
        events = list(_iter_sse_events(r))
        self.assertTrue(events, "No SSE events received")
        self.assertEqual(events[-1].get("type"), "done")


class TestPackageEndpoint(unittest.TestCase):

    def setUp(self):
        env_patcher = patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test-dummy"})
        env_patcher.start()
        self.addCleanup(env_patcher.stop)
        import app as app_module
        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()
        self.app_module = app_module

    ITEMS = [
        {"name": "Access Control Policy", "text": "MFA required. RBAC enforced."},
        {"name": "Incident Response Plan", "text": "Incidents classified P1-P4. SLA: P1 < 1h."},
        {"name": "Backup Policy", "text": "Daily backups to offsite S3. RTO 4h, RPO 1h."},
    ]

    def test_package_happy_path(self):
        """Multiple items produce a streaming report."""
        mock_stream = _make_mock_stream(json.dumps(GOOD_MAPPING))
        with patch.object(self.app_module.client.messages, "stream", return_value=mock_stream):
            r = self.client.post("/api/package", json={
                "evidence_items": self.ITEMS,
                "organization": "Acme Corp",
                "audit_period": "2025 Annual",
                "frameworks": ["ISO 27001", "SOC 2"],
            })
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/event-stream", r.content_type)

    def test_package_empty_items(self):
        """Empty evidence_items list must return 400."""
        r = self.client.post("/api/package", json={"evidence_items": []})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_package_missing_items_key(self):
        """Missing evidence_items key must return 400."""
        r = self.client.post("/api/package", json={"organization": "Acme"})
        self.assertEqual(r.status_code, 400)

    def test_package_single_item(self):
        """Packaging a single item is valid."""
        mock_stream = _make_mock_stream(json.dumps(GOOD_MAPPING))
        with patch.object(self.app_module.client.messages, "stream", return_value=mock_stream):
            r = self.client.post("/api/package", json={"evidence_items": [self.ITEMS[0]]})
        self.assertEqual(r.status_code, 200)

    def test_package_item_with_no_name(self):
        """Item missing 'name' key should not crash — defaults applied."""
        items = [{"text": "Anonymous policy text with no name field."}]
        mock_stream = _make_mock_stream(json.dumps(GOOD_MAPPING))
        with patch.object(self.app_module.client.messages, "stream", return_value=mock_stream):
            r = self.client.post("/api/package", json={"evidence_items": items})
        self.assertEqual(r.status_code, 200)

    def test_package_item_with_no_text(self):
        """Item missing 'text' key should not crash (empty string used)."""
        items = [{"name": "Empty item"}, {"name": "Real item", "text": "Some actual policy."}]
        mock_stream = _make_mock_stream(json.dumps(GOOD_MAPPING))
        with patch.object(self.app_module.client.messages, "stream", return_value=mock_stream):
            r = self.client.post("/api/package", json={"evidence_items": items})
        self.assertEqual(r.status_code, 200)

    def test_package_large_number_of_items(self):
        """Packaging 20 items should not crash."""
        items = [{"name": f"Policy {i}", "text": f"Policy body {i}: MFA enforced at level {i}."} for i in range(20)]
        mock_stream = _make_mock_stream(json.dumps(GOOD_MAPPING))
        with patch.object(self.app_module.client.messages, "stream", return_value=mock_stream):
            r = self.client.post("/api/package", json={"evidence_items": items})
        self.assertEqual(r.status_code, 200)

    def test_package_missing_organization_defaults(self):
        """Missing organization defaults to 'Organization', should not crash."""
        mock_stream = _make_mock_stream(json.dumps(GOOD_MAPPING))
        with patch.object(self.app_module.client.messages, "stream", return_value=mock_stream):
            r = self.client.post("/api/package", json={"evidence_items": self.ITEMS})
        self.assertEqual(r.status_code, 200)

    def test_package_xss_in_organization_name(self):
        """XSS in organization name must not crash the server."""
        xss_org = '<img src=x onerror=alert(1)>'
        mock_stream = _make_mock_stream(json.dumps(GOOD_MAPPING))
        with patch.object(self.app_module.client.messages, "stream", return_value=mock_stream):
            r = self.client.post("/api/package", json={
                "evidence_items": self.ITEMS,
                "organization": xss_org,
            })
        self.assertEqual(r.status_code, 200)


class TestFrontendRoute(unittest.TestCase):

    def setUp(self):
        env_patcher = patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test-dummy"})
        env_patcher.start()
        self.addCleanup(env_patcher.stop)
        import app as app_module
        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()

    def test_index_serves_html(self):
        """GET / must return 200 with HTML content."""
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"<!DOCTYPE html>", r.data)

    def test_unknown_route_404(self):
        """Unknown routes return 404."""
        r = self.client.get("/api/nonexistent")
        self.assertEqual(r.status_code, 404)

    def test_get_on_analyze_returns_405(self):
        """GET /api/analyze must return 405 Method Not Allowed."""
        r = self.client.get("/api/analyze")
        self.assertEqual(r.status_code, 405)

    def test_get_on_package_returns_405(self):
        """GET /api/package must return 405 Method Not Allowed."""
        r = self.client.get("/api/package")
        self.assertEqual(r.status_code, 405)


class TestControlsData(unittest.TestCase):

    def test_iso_controls_coverage(self):
        """ISO 27001 data must include all four annex domains."""
        from controls_data import ISO_27001_CONTROLS
        for domain in ["A.5", "A.6", "A.7", "A.8"]:
            self.assertIn(domain, ISO_27001_CONTROLS, f"Missing domain {domain}")

    def test_iso_control_count(self):
        """ISO 27001 must have at least 90 individual controls."""
        from controls_data import ISO_27001_CONTROLS
        total = sum(len(d["controls"]) for d in ISO_27001_CONTROLS.values())
        self.assertGreaterEqual(total, 90, f"Only {total} controls found")

    def test_soc2_categories_present(self):
        """SOC 2 must include CC1–CC9 plus A1, C1, PI1, P1."""
        from controls_data import SOC2_CONTROLS
        for cat in ["CC1", "CC2", "CC3", "CC4", "CC5", "CC6", "CC7", "CC8", "CC9", "A1", "C1", "PI1", "P1"]:
            self.assertIn(cat, SOC2_CONTROLS, f"Missing category {cat}")

    def test_build_controls_reference_contains_both_frameworks(self):
        """Reference string must mention both ISO 27001 and SOC 2."""
        from controls_data import build_controls_reference
        ref = build_controls_reference()
        self.assertIn("ISO 27001", ref)
        self.assertIn("SOC 2", ref)
        self.assertIn("A.8", ref)
        self.assertIn("CC6", ref)

    def test_build_controls_reference_is_string(self):
        """build_controls_reference() must return a non-empty string."""
        from controls_data import build_controls_reference
        ref = build_controls_reference()
        self.assertIsInstance(ref, str)
        self.assertGreater(len(ref), 500)

    def test_no_duplicate_control_ids_iso(self):
        """No control ID should appear twice in ISO 27001."""
        from controls_data import ISO_27001_CONTROLS
        all_ids = []
        for d in ISO_27001_CONTROLS.values():
            all_ids.extend(d["controls"].keys())
        self.assertEqual(len(all_ids), len(set(all_ids)), "Duplicate ISO control IDs found")

    def test_no_duplicate_control_ids_soc2(self):
        """No criterion ID should appear twice in SOC 2."""
        from controls_data import SOC2_CONTROLS
        all_ids = []
        for cat in SOC2_CONTROLS.values():
            key = "controls" if "controls" in cat else "criteria"
            all_ids.extend(cat[key].keys())
        dupes = [x for x in all_ids if all_ids.count(x) > 1]
        self.assertEqual(dupes, [], f"Duplicate SOC 2 IDs: {set(dupes)}")


class TestSettingsEndpoint(unittest.TestCase):
    """The in-app API key settings used by the desktop installer."""

    def setUp(self):
        import app as app_module
        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()
        self.app_module = app_module
        self._orig_key = app_module.client.api_key
        self.addCleanup(setattr, app_module.client, "api_key", self._orig_key)

    def test_get_reports_status_without_leaking_key(self):
        self.app_module.client.api_key = "sk-ant-secret-value-1234567890"
        r = self.client.get("/api/settings")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"api_key_configured": True})
        self.assertNotIn(b"secret-value", r.data)

    def test_get_reports_missing_key(self):
        self.app_module.client.api_key = None
        self.assertFalse(self.client.get("/api/settings").get_json()["api_key_configured"])

    def test_save_rejects_malformed_keys(self):
        for bad in ["", "   ", "hello", "sk-ant-short", "sk-ant-has space inside-1234567890", None, 123]:
            with patch.object(self.app_module.key_store, "save_key") as save:
                r = self.client.post("/api/settings", json={"api_key": bad})
            self.assertEqual(r.status_code, 400, bad)
            save.assert_not_called()

    def test_save_accepts_valid_key_and_never_echoes_it(self):
        good = "sk-ant-api03-" + "x" * 30
        with patch.object(self.app_module.key_store, "save_key") as save:
            r = self.client.post("/api/settings", json={"api_key": good})
        self.assertEqual(r.status_code, 200)
        save.assert_called_once_with(good)
        self.assertEqual(self.app_module.client.api_key, good)
        self.assertNotIn(good.encode(), r.data)

    def test_analyze_without_key_streams_clear_error(self):
        self.app_module.client.api_key = None
        r = self.client.post("/api/analyze", json={"evidence_text": "policy text", "frameworks": ["ISO 27001"]})
        events = list(_iter_sse_events(r))
        self.assertEqual(events[0]["type"], "error")
        self.assertIn("API key", events[0]["message"])

    def test_package_without_key_streams_clear_error(self):
        self.app_module.client.api_key = None
        r = self.client.post("/api/package", json={"evidence_items": [{"name": "a", "text": "b"}]})
        self.assertEqual(list(_iter_sse_events(r))[0]["type"], "error")


class TestKeyStore(unittest.TestCase):
    """Round-trip through the real encryption, in a throw-away directory."""

    def test_round_trip_delete_and_corruption(self):
        import tempfile
        from pathlib import Path
        import key_store
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(key_store, "user_data_dir", return_value=Path(tmp)):
                self.assertEqual(key_store.load_key(), "")
                key_store.save_key("  sk-ant-api03-roundtrip-0123456789  ")
                self.assertEqual(key_store.load_key(), "sk-ant-api03-roundtrip-0123456789")
                self.assertNotIn(b"roundtrip", (Path(tmp) / "api_key.dat").read_bytes())
                (Path(tmp) / "api_key.dat").write_bytes(b"dpapi:not-valid-base64!!")
                self.assertEqual(key_store.load_key(), "")
                key_store.save_key("sk-ant-api03-again-0123456789")
                key_store.delete_key()
                self.assertEqual(key_store.load_key(), "")


# ── Runner ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    loader = unittest.TestLoader()
    suite  = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestControlsData))
    suite.addTests(loader.loadTestsFromTestCase(TestFrontendRoute))
    suite.addTests(loader.loadTestsFromTestCase(TestAnalyzeEndpoint))
    suite.addTests(loader.loadTestsFromTestCase(TestPackageEndpoint))
    suite.addTests(loader.loadTestsFromTestCase(TestSettingsEndpoint))
    suite.addTests(loader.loadTestsFromTestCase(TestKeyStore))

    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
