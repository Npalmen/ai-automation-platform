"""Tests for ensure_runtime_schema — the startup schema safeguard."""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest


def _run(side_effect=None):
    from app.repositories.postgres.schema_migrations import ensure_runtime_schema

    engine = MagicMock()
    conn = MagicMock()
    # engine.begin() used as context manager
    engine.begin.return_value.__enter__ = MagicMock(return_value=conn)
    engine.begin.return_value.__exit__ = MagicMock(return_value=False)

    if side_effect:
        conn.execute.side_effect = side_effect

    return engine, conn, ensure_runtime_schema


class TestEnsureRuntimeSchemaHappyPath:
    def test_runs_without_raising(self):
        engine, conn, fn = _run()
        fn(engine)  # must not raise

    def test_executes_alter_for_each_required_column(self):
        from app.repositories.postgres.schema_migrations import _REQUIRED_COLUMNS

        engine, conn, fn = _run()
        fn(engine)
        assert conn.execute.call_count == len(_REQUIRED_COLUMNS)

    def test_alter_contains_add_column_if_not_exists(self):
        engine, conn, fn = _run()
        fn(engine)
        sql_str = str(conn.execute.call_args_list[0][0][0])
        assert "ADD COLUMN IF NOT EXISTS" in sql_str.upper()

    def test_alter_targets_tenant_configs_settings(self):
        engine, conn, fn = _run()
        fn(engine)
        sql_str = str(conn.execute.call_args_list[0][0][0])
        assert "tenant_configs" in sql_str
        assert "settings" in sql_str

    def test_alter_uses_json_type(self):
        engine, conn, fn = _run()
        fn(engine)
        sql_str = str(conn.execute.call_args_list[0][0][0])
        assert "JSON" in sql_str.upper()

    def test_uses_engine_begin_context_manager(self):
        engine, conn, fn = _run()
        fn(engine)
        engine.begin.assert_called_once()

    def test_idempotent_second_call(self):
        engine, conn, fn = _run()
        fn(engine)
        fn(engine)
        # Each call uses engine.begin once; both succeed without raising
        assert engine.begin.call_count == 2


class TestEnsureRuntimeSchemaErrorHandling:
    def test_db_error_raises_runtime_error(self):
        engine, conn, fn = _run(side_effect=Exception("column already exists"))
        with pytest.raises(RuntimeError, match="Runtime schema migration failed"):
            fn(engine)

    def test_runtime_error_wraps_original(self):
        original = Exception("some pg error")
        engine, conn, fn = _run(side_effect=original)
        with pytest.raises(RuntimeError) as exc_info:
            fn(engine)
        assert exc_info.value.__cause__ is original

    def test_error_detail_in_message(self):
        engine, conn, fn = _run(side_effect=Exception("permission denied"))
        with pytest.raises(RuntimeError) as exc_info:
            fn(engine)
        assert "permission denied" in str(exc_info.value)

    def test_logs_error_on_failure(self):
        engine, conn, fn = _run(side_effect=Exception("oops"))
        with (
            patch("app.repositories.postgres.schema_migrations.log") as mock_log,
            pytest.raises(RuntimeError),
        ):
            fn(engine)
        mock_log.error.assert_called_once()

    def test_logs_success_on_completion(self):
        engine, conn, fn = _run()
        with patch("app.repositories.postgres.schema_migrations.log") as mock_log:
            fn(engine)
        mock_log.info.assert_called_once()
        assert "complete" in mock_log.info.call_args[0][0].lower()


class TestRequiredColumnsRegistry:
    def test_required_columns_is_list(self):
        from app.repositories.postgres.schema_migrations import _REQUIRED_COLUMNS
        assert isinstance(_REQUIRED_COLUMNS, list)

    def test_settings_entry_present(self):
        from app.repositories.postgres.schema_migrations import _REQUIRED_COLUMNS
        tables_cols = [(t, c) for t, c, _ in _REQUIRED_COLUMNS]
        assert ("tenant_configs", "settings") in tables_cols

    def test_each_entry_is_3_tuple(self):
        from app.repositories.postgres.schema_migrations import _REQUIRED_COLUMNS
        for entry in _REQUIRED_COLUMNS:
            assert len(entry) == 3, f"Entry {entry} must have (table, column, type)"


class TestStartupIntegration:
    def test_ensure_runtime_schema_called_at_startup(self):
        """Verify on_startup calls ensure_runtime_schema after create_all."""
        import app.main as main_module
        import inspect

        src = inspect.getsource(main_module.on_startup)
        assert "ensure_runtime_schema" in src

    def test_ensure_runtime_schema_called_after_create_all(self):
        import app.main as main_module
        import inspect

        src = inspect.getsource(main_module.on_startup)
        # Find the call sites (not the import line)
        call_ca = src.index("create_all(")
        call_rs = src.index("ensure_runtime_schema(")
        assert call_rs > call_ca, (
            "ensure_runtime_schema must be called after create_all"
        )
