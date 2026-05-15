"""Phase 4 — Functional tests for DirectConnection against a live sshd fixture.

Each test creates a fresh DirectConnection from spawn_sshd fixture data and
closes it in teardown via try/finally.
"""

import pytest
from agent.connectionpool.config_loader import ConnectionConfig
from agent.connectionpool.connection import DirectConnection, ConnectionState


def _make_config(spawn_sshd) -> ConnectionConfig:
    return ConnectionConfig(
        name="test-node",
        user=spawn_sshd.user,
        id_file=spawn_sshd.client_key_path,
        mode="direct",
        port=spawn_sshd.port,
        host=spawn_sshd.host,
    )


@pytest.mark.functional
@pytest.mark.requires_sshd
def test_connection_open_succeeds(spawn_sshd):
    """connection.open() completes without raising an exception."""
    config = _make_config(spawn_sshd)
    connection = DirectConnection(config)
    try:
        connection.open()
    finally:
        connection.close()


@pytest.mark.functional
@pytest.mark.requires_sshd
def test_connection_state_open_after_open(spawn_sshd):
    """connection.get_state() returns ConnectionState.OPEN after a successful open()."""
    config = _make_config(spawn_sshd)
    connection = DirectConnection(config)
    try:
        connection.open()
        assert connection.get_state() == ConnectionState.OPEN
    finally:
        connection.close()


@pytest.mark.functional
@pytest.mark.requires_sshd
def test_connection_execute_echo(spawn_sshd):
    """connection.execute('echo hello') returns stdout containing 'hello' and exit_code 0."""
    config = _make_config(spawn_sshd)
    connection = DirectConnection(config)
    try:
        connection.open()
        result = connection.execute("echo hello")
        assert result.exit_code == 0
        assert "hello" in result.stdout
    finally:
        connection.close()


@pytest.mark.functional
@pytest.mark.requires_sshd
def test_connection_close(spawn_sshd):
    """connection.close() completes without raising an exception."""
    config = _make_config(spawn_sshd)
    connection = DirectConnection(config)
    try:
        connection.open()
    finally:
        connection.close()  # must not raise


@pytest.mark.functional
@pytest.mark.requires_sshd
def test_connection_state_closed_after_close(spawn_sshd):
    """connection.get_state() returns ConnectionState.CLOSED after close()."""
    config = _make_config(spawn_sshd)
    connection = DirectConnection(config)
    try:
        connection.open()
    finally:
        connection.close()
    assert connection.get_state() == ConnectionState.CLOSED
