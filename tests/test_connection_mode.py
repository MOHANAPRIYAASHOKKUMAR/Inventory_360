"""Connection mode selection must fail closed inside Snowflake (never the owner's identity)."""
import pytest

from inventory360.data_access import connection


@pytest.fixture
def env(monkeypatch, tmp_path):
    for var in ("SNOWFLAKE_HOST", "SNOWFLAKE_DEFAULT_CONNECTION_NAME", "SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER",
                "INV360_ALLOW_SERVICE_IDENTITY", "INV360_CALLERS_RIGHTS"):
        monkeypatch.delenv(var, raising=False)
    token = tmp_path / "token"
    token.write_text("t")
    monkeypatch.setattr(connection, "SPCS_TOKEN_PATH", token)
    return monkeypatch


def _headers(env, available: bool | None):
    """available=None simulates the header check raising."""
    def check():
        if available is None:
            raise RuntimeError("no script context")
        return available
    env.setattr(connection, "_callers_rights_available", lambda: _safe(check))


def _safe(fn):
    try:
        return fn()
    except Exception:  # noqa: BLE001 - mirrors the production guard
        return False


def test_in_snowflake_with_viewer_token_uses_callers_rights(env):
    env.setenv("SNOWFLAKE_HOST", "acct.snowflakecomputing.com")
    _headers(env, True)
    assert connection.connection_mode() == "callers"


@pytest.mark.parametrize("available", [False, None])
def test_in_snowflake_without_viewer_token_is_denied(env, available):
    env.setenv("SNOWFLAKE_HOST", "acct.snowflakecomputing.com")
    _headers(env, available)
    assert connection.connection_mode() == "denied"


def test_service_identity_needs_explicit_opt_in(env):
    env.setenv("SNOWFLAKE_HOST", "acct.snowflakecomputing.com")
    _headers(env, False)
    env.setenv("INV360_ALLOW_SERVICE_IDENTITY", "true")
    assert connection.connection_mode() == "spcs"


def test_denied_mode_refuses_to_connect(env):
    env.setenv("SNOWFLAKE_HOST", "acct.snowflakecomputing.com")
    _headers(env, False)
    with pytest.raises(connection.DataAccessDenied):
        connection.get_connection()


def test_local_named_connection(env):
    env.setenv("SNOWFLAKE_DEFAULT_CONNECTION_NAME", "dev")
    assert connection.connection_mode() == "named"
