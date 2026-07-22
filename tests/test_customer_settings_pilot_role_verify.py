"""Tests for pilot Customer Settings role verifier (mocked — no pilot/CI browser)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from scripts import customer_settings_pilot_role_verify as verify


class TestParsing:
    def test_resolve_roles_all(self):
        assert verify.resolve_roles("all") == list(verify.ROLE_ORDER)

    def test_resolve_roles_single(self):
        assert verify.resolve_roles("operations") == ["operations"]

    def test_resolve_roles_invalid(self):
        with pytest.raises(ValueError):
            verify.resolve_roles("bogus")

    def test_operator_id(self):
        assert verify.operator_id("Admin") == "operator-admin"

    def test_parse_args_defaults(self):
        args = verify.parse_args([])
        assert args.role == "all"
        assert args.tenant_id == verify.DEFAULT_TENANT
        assert args.restore_admin_role == "admin"


class TestEnvRestore:
    def test_read_write_production_env(self, tmp_path: Path):
        env_file = tmp_path / ".env.production"
        env_file.write_text("ADMIN_ROLE=operations\nFOO=bar\n", encoding="utf-8")
        state = verify.read_production_env(env_file)
        assert state.admin_role == "operations"
        verify.write_production_env(verify.EnvState("admin", "operator-test"), env_file)
        text = env_file.read_text(encoding="utf-8")
        assert "ADMIN_ROLE=admin" in text
        assert "SUPER_ADMIN_OPERATOR_IDS=operator-test" in text
        assert "FOO=bar" in text

    def test_manual_restore_command_has_no_secrets(self):
        cmd = verify.manual_restore_command("admin")
        assert "password" not in cmd.lower()
        assert "ADMIN_ROLE=admin" in cmd


class TestApiMatrix:
    def _session_with_aggregate(self, aggregate: dict):
        sess = MagicMock()

        def request(method, url, **kwargs):
            resp = MagicMock()
            if method == "GET" and url.endswith("/settings"):
                resp.status_code = 200
                resp.json.return_value = aggregate
            elif method == "GET" and "/settings/" in url:
                resp.status_code = 200
                resp.json.return_value = {"domain": "x"}
            elif method == "PATCH":
                domain = url.rsplit("/", 1)[-1]
                if domain == "identity":
                    resp.status_code = 403
                elif domain == "integrations":
                    resp.status_code = 403
                else:
                    resp.status_code = 403
                resp.json.return_value = {"detail": "forbidden"}
            resp.text = "{}"
            return resp

        sess.request.side_effect = request
        return sess

    def test_read_only_patch_forbidden(self):
        agg = {"config_version": 5, "permissions": {}}
        sess = self._session_with_aggregate(agg)
        ctx = verify.RunContext(
            base_url="https://api.krowolf.se",
            tenant_id="T_TEST",
            username="u",
            password="p",
            restore_admin_role="admin",
            skip_browser=True,
            report_path=Path("report.json"),
            env_file=Path("env"),
        )
        with patch.object(verify, "session_me", return_value={"operator": {"role": "read_only"}}):
            checks, done = verify.run_api_role_checks("read_only", ctx, sess, admin_mutation_done=False)
        assert not done
        assert checks.overall() == "PASS"
        names = [c["name"] for c in checks.items]
        assert "patch_identity_403" in names

    def test_operations_routing_preview_only(self):
        agg = {
            "config_version": 3,
            "permissions": {"routing": {"write": True}, "integrations": {"write": False}},
        }
        sess = MagicMock()

        def request(method, url, **kwargs):
            resp = MagicMock()
            if method == "GET" and url.endswith("/settings"):
                resp.status_code = 200
                resp.json.return_value = agg
            elif method == "GET":
                resp.status_code = 200
                resp.json.return_value = {}
            elif method == "POST" and url.endswith("/preview"):
                resp.status_code = 200
                resp.json.return_value = {"valid": True}
            elif method == "PATCH":
                resp.status_code = 403
                resp.json.return_value = {}
            return resp

        sess.request.side_effect = request
        ctx = verify.RunContext(
            base_url="https://api.krowolf.se",
            tenant_id="T_TEST",
            username="u",
            password="p",
            restore_admin_role="admin",
            skip_browser=True,
            report_path=Path("report.json"),
            env_file=Path("env"),
        )
        with patch.object(verify, "session_me", return_value={"operator": {"role": "operations"}}):
            checks, done = verify.run_api_role_checks("operations", ctx, sess, admin_mutation_done=False)
        assert not done
        assert any(c["name"] == "routing_preview" and c["status"] == "PASS" for c in checks.items)

    def test_admin_timezone_roundtrip_at_most_two_patches(self):
        agg = {"config_version": 5, "permissions": {}, "domains": {"identity": {"timezone": "Europe/Stockholm"}}}
        version = {"v": 5}

        def request(method, url, **kwargs):
            resp = MagicMock()
            if method == "GET" and url.endswith("/settings"):
                resp.status_code = 200
                resp.json.return_value = {**agg, "config_version": version["v"]}
            elif method == "GET":
                resp.status_code = 200
                resp.json.return_value = {}
            elif method == "POST":
                resp.status_code = 200
                resp.json.return_value = {"valid": True}
            elif method == "PATCH":
                body = kwargs.get("json") or {}
                if body.get("expected_config_version", 0) > version["v"] + 1:
                    resp.status_code = 409
                    resp.json.return_value = {"detail": "conflict"}
                else:
                    version["v"] += 1
                    resp.status_code = 200
                    resp.json.return_value = {"config_version": version["v"]}
            return resp

        sess = MagicMock()
        sess.request.side_effect = request
        ctx = verify.RunContext(
            base_url="https://api.krowolf.se",
            tenant_id="T_TEST",
            username="u",
            password="p",
            restore_admin_role="admin",
            skip_browser=True,
            report_path=Path("report.json"),
            env_file=Path("env"),
            pre_snapshot={"timezone": "Europe/Stockholm"},
        )
        with patch.object(verify, "session_me", return_value={"operator": {"role": "admin"}}):
            checks, done = verify.run_api_role_checks("admin", ctx, sess, admin_mutation_done=False)
        assert done
        assert version["v"] <= 7
        assert ctx.mutations[0]["status"] == "PASS"


class TestReport:
    def test_report_redaction(self, tmp_path: Path):
        secrets = {"hunter2"}
        payload = {"note": "password=hunter2", "ok": True}
        path = tmp_path / "report.json"
        verify.write_json_report(path, payload, secrets)
        text = path.read_text(encoding="utf-8")
        assert "hunter2" not in text
        assert "[REDACTED]" in text

    def test_build_report_shape(self):
        ctx = verify.RunContext(
            base_url="https://api.krowolf.se",
            tenant_id="T_TEST",
            username="u",
            password="p",
            restore_admin_role="admin",
            skip_browser=True,
            report_path=Path("report.json"),
            env_file=Path("env"),
            original_env=verify.EnvState("admin", "operator-admin"),
            runtime_code_sha="abc",
            release_id="rc-abc",
            restore_status="PASS",
        )
        report = verify.build_report(ctx, side_effect={"ok": True, "delta": {}}, overall="PASS")
        assert report["schema_version"] == 1
        assert report["overall_status"] == "PASS"
        assert "password" not in json.dumps(report)


class TestSnapshots:
    def test_compare_snapshots_ok(self):
        before = {
            "jobs": 0,
            "approvals": 0,
            "scheduler": "paused",
            "gmail_fp": "a",
            "visma_fp": "b",
            "activation_snapshots": 0,
            "onboarding_sessions": 0,
            "timezone": "Europe/Stockholm",
            "admin_role": "admin",
            "super_admin_operator_ids_present": True,
            "config_version": 5,
        }
        after = dict(before)
        after["config_version"] = 7
        result = verify.compare_snapshots(before, after, start_timezone="Europe/Stockholm")
        assert result["config_version_delta"] == 2
        assert result["ok"] is True


class TestRestoreFlow:
    def test_restore_on_success(self, tmp_path: Path):
        env_file = tmp_path / ".env.production"
        env_file.write_text("ADMIN_ROLE=read_only\n", encoding="utf-8")
        original = verify.EnvState("admin", "")
        with patch.object(verify, "ENV_PRODUCTION", env_file), patch.object(verify, "COMPOSE_FILE", tmp_path / "compose.yml"), patch.object(
            verify, "restart_app_container"
        ) as restart:
            verify.restore_production_env(original)
            restart.assert_called_once()
        assert "ADMIN_ROLE=admin" in env_file.read_text(encoding="utf-8")

    def test_super_admin_env_adds_operator_id(self, tmp_path: Path):
        env_file = tmp_path / ".env.production"
        env_file.write_text("ADMIN_ROLE=admin\nSUPER_ADMIN_OPERATOR_IDS=operator-admin\n", encoding="utf-8")
        original = verify.read_production_env(env_file)
        with patch.object(verify, "ENV_PRODUCTION", env_file), patch.object(verify, "COMPOSE_FILE", tmp_path / "c.yml"), patch.object(
            verify, "restart_app_container"
        ):
            verify.set_pilot_role("super_admin", "browseruser", original=original)
        updated = env_file.read_text(encoding="utf-8")
        assert "operator-browseruser" in updated
        assert "ADMIN_ROLE=admin" in updated

    def test_run_verification_restores_on_failure(self, tmp_path: Path, monkeypatch):
        env_file = tmp_path / ".env.browser-test"
        env_file.write_text(
            "\n".join(
                [
                    "K12_BROWSER_BASE_URL=https://api.krowolf.se",
                    "K12_BROWSER_USERNAME=tester",
                    "K12_BROWSER_PASSWORD=secret",
                    "K12_BROWSER_ROLE=read_only",
                ]
            ),
            encoding="utf-8",
        )
        prod = tmp_path / ".env.production"
        prod.write_text("ADMIN_ROLE=admin\n", encoding="utf-8")
        args = verify.parse_args(
            [
                "--env-file",
                str(env_file),
                "--report-path",
                str(tmp_path / "report.json"),
                "--skip-browser",
                "--role",
                "read_only",
            ]
        )
        monkeypatch.setattr(verify, "ENV_PRODUCTION", prod)
        monkeypatch.setattr(verify, "COMPOSE_FILE", tmp_path / "compose.yml")
        monkeypatch.setattr(verify, "PENDING_RESTORE", tmp_path / "pending.json")
        monkeypatch.setattr(verify, "wait_health", lambda *_a, **_k: True)
        monkeypatch.setattr(verify, "fetch_runtime_identity", lambda: ("sha", "rc-sha"))
        monkeypatch.setattr(verify, "snapshot_sql", lambda _t: {"scheduler": "paused", "timezone": "Europe/Stockholm", "jobs": 0, "approvals": 0, "gmail_fp": "x", "visma_fp": "y", "activation_snapshots": 0, "onboarding_sessions": 0, "admin_role": "admin", "super_admin_operator_ids_present": False, "config_version": 1})
        monkeypatch.setattr(verify, "set_pilot_role", lambda *a, **k: None)
        monkeypatch.setattr(verify, "restart_app_container", lambda *a, **k: None)

        sess = MagicMock()
        monkeypatch.setattr(verify, "session_login", lambda *a, **k: sess)
        monkeypatch.setattr(verify, "session_me", lambda *a, **k: {"operator": {"role": "read_only"}})

        def fake_api(role, ctx, s, admin_mutation_done=False):
            checks = verify.Checks()
            checks.add("forced_fail", "FAIL", "boom")
            return checks, admin_mutation_done

        monkeypatch.setattr(verify, "run_api_role_checks", fake_api)
        code = verify.run_verification(args)
        assert code == 1
        report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
        assert report["restore_status"] == "PASS"
        assert "secret" not in json.dumps(report)


class TestSecretScan:
    def test_scan_for_secrets(self):
        assert verify.scan_for_secrets("access_token=abc") is True
        assert verify.scan_for_secrets("normal text") is False
