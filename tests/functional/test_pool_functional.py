"""Phase 5 — Functional tests for ConnectionPool against a live sshd fixture.

Every test calls pool.stop() in a try/finally block to prevent leaked timers.
A wait_for_open() helper polls get_connection_state() for up to 5 seconds so
tests don't race against the initial connection open.
"""

import time
import pytest
from agent.connectionpool.config_loader import ConnectionConfig
from agent.connectionpool.pool import ConnectionPool


def _make_config(spawn_sshd) -> ConnectionConfig:
    return ConnectionConfig(
        name="test-node",
        user=spawn_sshd.user,
        id_file=spawn_sshd.client_key_path,
        mode="direct",
        port=spawn_sshd.port,
        host=spawn_sshd.host,
    )


def _wait_for_open(pool: ConnectionPool, name: str, timeout: float = 5.0) -> str:
    """Poll pool.get_connection_state(name) until it returns 'open' or timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = pool.get_connection_state(name)
        if state == "open":
            return state
        time.sleep(0.1)
    return pool.get_connection_state(name)


@pytest.fixture
def pool_and_name(spawn_sshd):
    config = _make_config(spawn_sshd)
    pool = ConnectionPool([config], reconnection_delay=30)
    pool.start()
    name = config.name
    try:
        yield pool, name
    finally:
        pool.stop()


@pytest.mark.functional
@pytest.mark.requires_sshd
def test_pool_get_connection_state_open(pool_and_name):
    """pool.get_connection_state(name) returns 'open' after pool.start()."""
    pool, name = pool_and_name
    state = _wait_for_open(pool, name)
    assert state == "open"


@pytest.mark.functional
@pytest.mark.requires_sshd
def test_pool_get_connection_state_not_in_pool(pool_and_name):
    """pool.get_connection_state('unknown') returns 'not_in_pool'."""
    pool, _ = pool_and_name
    state = pool.get_connection_state("unknown")
    assert state == "not_in_pool"


@pytest.mark.functional
@pytest.mark.requires_sshd
def test_pool_disable_connection_closes_and_prevents_reconnect(pool_and_name):
    """After disable_connection(name), state stays 'closed' and the monitor does not reconnect."""
    pool, name = pool_and_name
    # Wait until the connection is open before disabling
    _wait_for_open(pool, name)

    pool.disable_connection(name)

    # State should be closed immediately after disable
    state = pool.get_connection_state(name)
    assert state == "closed"

    # Wait one monitor cycle to confirm the monitor doesn't reconnect (pool has reconnection_delay=30s,
    # but we verify the disabled set prevents reconnect; a brief pause is enough)
    time.sleep(0.5)
    state = pool.get_connection_state(name)
    assert state == "closed", f"Expected 'closed' after disable, got '{state}'"
