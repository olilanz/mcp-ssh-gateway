import logging
from unittest.mock import MagicMock, patch

from agent.connectionpool.config_loader import ConnectionConfig
from agent.connectionpool.connection import ConnectionState
from agent.connectionpool.pool import ConnectionPool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pool_with_fake_connections(names):
    """Return a ConnectionPool whose self.connections are MagicMock objects.

    The pool is built with an empty config list so no real Connection objects
    are created, then the fake connections are injected directly.
    """
    pool = ConnectionPool([])
    for name in names:
        conn = MagicMock()
        conn.name = name
        conn.get_state.return_value = ConnectionState.OPEN
        pool.connections.append(conn)
    return pool


def test_connection_pool_accepts_dict_configs(monkeypatch):
    captured = []

    class FakeConnection:
        def __init__(self, *args, **kwargs):
            captured.append({"args": args, "kwargs": kwargs})

    monkeypatch.setattr("agent.connectionpool.pool.Connection", FakeConnection)

    connection_configs = [
        {
            "name": "dict-connection",
            "user": "user",
            "id_file": "/tmp/id_rsa",
            "mode": "direct",
            "port": 22,
            "host": "127.0.0.1",
        }
    ]

    pool = ConnectionPool(connection_configs)

    assert len(pool.connections) == 1
    assert captured[0]["args"] == ()
    assert captured[0]["kwargs"]["name"] == "dict-connection"


def test_connection_pool_accepts_connection_config_objects(monkeypatch):
    captured = []

    class FakeConnection:
        def __init__(self, *args, **kwargs):
            captured.append({"args": args, "kwargs": kwargs})

    monkeypatch.setattr("agent.connectionpool.pool.Connection", FakeConnection)

    connection_configs = [
        ConnectionConfig(
            name="object-connection",
            user="user",
            id_file="/tmp/id_rsa",
            mode="direct",
            port=22,
            host="127.0.0.1",
        )
    ]

    pool = ConnectionPool(connection_configs)

    assert len(pool.connections) == 1
    assert len(captured[0]["args"]) == 1
    assert captured[0]["args"][0].name == "object-connection"


# ---------------------------------------------------------------------------
# disable_connection tests
# ---------------------------------------------------------------------------

def test_disable_connection_marks_disabled():
    """After disable_connection the name is in _disabled_names."""
    pool = _make_pool_with_fake_connections(["alpha"])
    pool.disable_connection("alpha")
    assert "alpha" in pool._disabled_names


def test_disable_connection_closes_active_connection():
    """disable_connection calls close() on the matching connection."""
    pool = _make_pool_with_fake_connections(["alpha"])
    conn = pool.connections[0]
    pool.disable_connection("alpha")
    conn.close.assert_called_once()


def test_disable_unknown_connection_logs_warning(caplog):
    """disable_connection on an unknown name logs a warning and does not raise."""
    pool = _make_pool_with_fake_connections([])
    with caplog.at_level(logging.WARNING, logger="root"):
        pool.disable_connection("nonexistent")
    assert any("nonexistent" in m for m in caplog.messages)


# ---------------------------------------------------------------------------
# enable_connection tests
# ---------------------------------------------------------------------------

def test_enable_connection_clears_disabled_mark():
    """After enable_connection the name is removed from _disabled_names."""
    pool = _make_pool_with_fake_connections(["beta"])
    pool._disabled_names.add("beta")
    pool.enable_connection("beta")
    assert "beta" not in pool._disabled_names


def test_enable_unknown_connection_logs_warning(caplog):
    """enable_connection on an unknown name logs a warning and does not raise."""
    pool = _make_pool_with_fake_connections([])
    with caplog.at_level(logging.WARNING, logger="root"):
        pool.enable_connection("nonexistent")
    assert any("nonexistent" in m for m in caplog.messages)


# ---------------------------------------------------------------------------
# remove_connection tests
# ---------------------------------------------------------------------------

def test_remove_connection_removes_from_pool():
    """After remove_connection the connection is absent from pool.connections."""
    pool = _make_pool_with_fake_connections(["gamma"])
    pool.remove_connection("gamma")
    assert all(c.name != "gamma" for c in pool.connections)


def test_remove_connection_closes_connection():
    """remove_connection calls close() on the matching connection."""
    pool = _make_pool_with_fake_connections(["gamma"])
    conn = pool.connections[0]
    pool.remove_connection("gamma")
    conn.close.assert_called_once()


def test_remove_unknown_connection_logs_warning(caplog):
    """remove_connection on an unknown name logs a warning and does not raise."""
    pool = _make_pool_with_fake_connections([])
    with caplog.at_level(logging.WARNING, logger="root"):
        pool.remove_connection("nonexistent")
    assert any("nonexistent" in m for m in caplog.messages)


# ---------------------------------------------------------------------------
# Monitor behaviour with disabled/enabled connections
# ---------------------------------------------------------------------------

def test_monitor_skips_disabled_connection():
    """Monitor does NOT call open() on a disabled connection even if it is closed."""
    pool = _make_pool_with_fake_connections(["delta"])
    conn = pool.connections[0]
    conn.get_state.return_value = ConnectionState.CLOSED  # not OPEN

    pool._disabled_names.add("delta")

    # Patch _schedule_monitor to avoid creating a real timer, but do NOT set
    # _stopping — the monitor returns early when stopping is set.
    with patch.object(pool, "_schedule_monitor"):
        pool._monitor_once()

    conn.open.assert_not_called()


def test_monitor_reopens_enabled_connection():
    """After enable_connection, monitor calls open() for a closed connection."""
    pool = _make_pool_with_fake_connections(["epsilon"])
    conn = pool.connections[0]
    conn.get_state.return_value = ConnectionState.CLOSED  # not OPEN

    # Start disabled then re-enable
    pool._disabled_names.add("epsilon")
    pool.enable_connection("epsilon")

    # Patch _schedule_monitor to avoid creating a real timer; do NOT set
    # _stopping so the monitor body actually runs.
    with patch.object(pool, "_schedule_monitor"), \
         patch.object(pool, "gather_os_info"):
        pool._monitor_once()

    conn.open.assert_called_once()


# ---------------------------------------------------------------------------
# get_connection_state tests (Cleanup 2)
# ---------------------------------------------------------------------------

def test_get_connection_state_open():
    """Pool with a mock open connection returns 'open'."""
    pool = _make_pool_with_fake_connections(["alpha"])
    pool.connections[0].get_state.return_value = ConnectionState.OPEN
    assert pool.get_connection_state("alpha") == "open"


def test_get_connection_state_not_in_pool():
    """Pool without matching name returns 'not_in_pool'."""
    pool = _make_pool_with_fake_connections([])
    assert pool.get_connection_state("nonexistent") == "not_in_pool"


def test_get_connection_state_broken():
    """Pool with a broken connection returns 'broken'."""
    pool = _make_pool_with_fake_connections(["zeta"])
    pool.connections[0].get_state.return_value = ConnectionState.BROKEN
    assert pool.get_connection_state("zeta") == "broken"


# ---------------------------------------------------------------------------
# query_pool tests (Cleanup 3)
# ---------------------------------------------------------------------------

def test_query_pool_uses_get_state():
    """query_pool returns list with 'state' key using get_state().value — no AttributeError."""
    pool = _make_pool_with_fake_connections(["theta"])
    pool.connections[0].get_state.return_value = ConnectionState.OPEN

    result = pool.query_pool()

    assert len(result) == 1
    assert result[0]["name"] == "theta"
    assert result[0]["state"] == "open"
    # Confirm the old broken keys are absent
    assert "is_running" not in result[0]
    assert "connection_state" not in result[0]


# ---------------------------------------------------------------------------
# Monitor disabled re-check test (Cleanup 4)
# ---------------------------------------------------------------------------

def test_monitor_rechecks_disabled_connection_before_open():
    """Monitor does NOT call open() when connection is in _disabled_names at re-check."""
    pool = _make_pool_with_fake_connections(["iota"])
    conn = pool.connections[0]
    conn.get_state.return_value = ConnectionState.CLOSED

    # Connection is already disabled before the monitor runs (covers the re-check path)
    pool._disabled_names.add("iota")

    with patch.object(pool, "_schedule_monitor"):
        pool._monitor_once()

    conn.open.assert_not_called()
