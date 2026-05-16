"""Unit tests for NodeService.run_command_on_node(), upload_file_to_node(),
and download_file_from_node().
"""

import pytest

from agent.nodes.models import NodeConfig
from agent.nodes.registry import NodeRegistry
from agent.nodes.service import NodeService
from tests.agent.nodes.conftest import make_node_config, make_mock_pool


# ---------------------------------------------------------------------------
# Helpers specific to execution tests
# ---------------------------------------------------------------------------


def _make_noop_handshake():
    """Return a MagicMock handshake service that does nothing (returns {})."""
    from unittest.mock import MagicMock
    hs = MagicMock()
    hs.run.return_value = {}
    return hs


def _make_service_with_open_connection(name="lab-pi-01"):
    """Build a NodeService where the named node is enabled and has an open mock connection."""
    from unittest.mock import MagicMock
    from agent.connectionpool.connection import ConnectionState

    registry = NodeRegistry()
    cfg = NodeConfig(
        name=name,
        mode="direct",
        enabled=True,
        host="192.168.1.10",
        port=22,
        user="pi",
        id_file=None,
    )
    registry.add(cfg)

    mock_conn = MagicMock()
    mock_conn.name = name

    pool = MagicMock()
    pool.get_connection_state.return_value = "open"
    pool.get_connection.return_value = mock_conn
    pool.ensure_connection_open.return_value = mock_conn

    hs = _make_noop_handshake()
    from unittest.mock import MagicMock as _MagicMock
    svc = NodeService(registry=registry, pool=pool, handshake_service=hs, agent_identity_service=_MagicMock())
    return svc, mock_conn


# ---------------------------------------------------------------------------
# NodeService — run_command_on_node() tests
# ---------------------------------------------------------------------------


def test_run_command_on_node_delegates_to_connection():
    """run_command_on_node() calls connection.execute() and returns to_dict() result."""
    from unittest.mock import MagicMock
    from datetime import datetime, timezone
    from agent.connection_result import CommandResult

    svc, mock_conn = _make_service_with_open_connection()

    fake_result = CommandResult(
        command="echo hi",
        exit_code=0,
        stdout="hi\n",
        stderr="",
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
    )
    mock_conn.execute.return_value = fake_result

    result = svc.run_command_on_node("lab-pi-01", "echo hi")

    assert "exit_code" in result
    assert "stdout" in result
    assert "stderr" in result
    assert result["exit_code"] == 0
    assert result["stdout"] == "hi\n"


def test_run_command_on_node_unknown_node_returns_error():
    """run_command_on_node() returns node not found error for unknown node."""
    from unittest.mock import MagicMock

    registry = NodeRegistry()
    pool = MagicMock()
    svc = NodeService(registry=registry, pool=pool, handshake_service=_make_noop_handshake(), agent_identity_service=MagicMock())

    result = svc.run_command_on_node("no-such-node", "echo hi")
    assert result == {"error": "node not found", "name": "no-such-node"}


def test_run_command_on_node_disabled_node_returns_error():
    """run_command_on_node() returns node_disabled error for a disabled node."""
    from unittest.mock import MagicMock

    registry = NodeRegistry()
    cfg = NodeConfig(
        name="lab-pi-01",
        mode="direct",
        enabled=False,
        host="192.168.1.10",
        port=22,
        user="pi",
        id_file=None,
    )
    registry.add(cfg)

    pool = MagicMock()
    svc = NodeService(registry=registry, pool=pool, handshake_service=_make_noop_handshake(), agent_identity_service=MagicMock())

    result = svc.run_command_on_node("lab-pi-01", "echo hi")
    assert result == {"error": "node_disabled", "name": "lab-pi-01"}


def test_run_command_on_node_not_in_pool_returns_error():
    """run_command_on_node() returns not_in_pool error when pool.get_connection returns None."""
    from unittest.mock import MagicMock

    registry = NodeRegistry()
    cfg = NodeConfig(
        name="lab-pi-01",
        mode="direct",
        enabled=True,
        host="192.168.1.10",
        port=22,
        user="pi",
        id_file=None,
    )
    registry.add(cfg)

    pool = MagicMock()
    pool.get_connection_state.return_value = "not_in_pool"
    pool.get_connection.return_value = None

    svc = NodeService(registry=registry, pool=pool, handshake_service=_make_noop_handshake(), agent_identity_service=MagicMock())

    result = svc.run_command_on_node("lab-pi-01", "echo hi")
    assert result == {"error": "not_in_pool", "name": "lab-pi-01"}


def test_run_command_on_node_timeout_returns_error():
    """run_command_on_node() returns timeout error when connection.execute raises TimeoutError."""
    svc, mock_conn = _make_service_with_open_connection()
    mock_conn.execute.side_effect = TimeoutError("timed out")

    result = svc.run_command_on_node("lab-pi-01", "sleep 100", timeout=1)

    assert result["error"] == "timeout"
    assert result["name"] == "lab-pi-01"
    assert result["command"] == "sleep 100"


# ---------------------------------------------------------------------------
# NodeService — upload_file_to_node() / download_file_from_node() tests
# ---------------------------------------------------------------------------


def test_upload_file_to_node_delegates_to_connection():
    """upload_file_to_node() calls connection.upload_file() with correct args and returns result."""
    import base64

    svc, mock_conn = _make_service_with_open_connection()
    mock_conn.upload_file.return_value = {"status": "written", "path": "/tmp/test"}

    valid_b64 = base64.b64encode(b"hello").decode()
    result = svc.upload_file_to_node("lab-pi-01", "/tmp/test", valid_b64, "0644")

    assert result == {"status": "written", "path": "/tmp/test"}
    mock_conn.upload_file.assert_called_once_with("/tmp/test", valid_b64, "0644")


def test_upload_file_to_node_disabled_node_returns_error():
    """upload_file_to_node() returns node_disabled error for a disabled node."""
    import base64
    from unittest.mock import MagicMock

    registry = NodeRegistry()
    cfg = NodeConfig(
        name="lab-pi-01",
        mode="direct",
        enabled=False,
        host="192.168.1.10",
        port=22,
        user="pi",
        id_file=None,
    )
    registry.add(cfg)

    pool = MagicMock()
    svc = NodeService(registry=registry, pool=pool, handshake_service=_make_noop_handshake(), agent_identity_service=MagicMock())

    valid_b64 = base64.b64encode(b"hello").decode()
    result = svc.upload_file_to_node("lab-pi-01", "/tmp/test", valid_b64, "0644")
    assert result == {"error": "node_disabled", "name": "lab-pi-01"}


def test_download_file_from_node_delegates_to_connection():
    """download_file_from_node() calls connection.download_file() and returns result."""
    import base64

    svc, mock_conn = _make_service_with_open_connection()
    expected = {"status": "ok", "path": "/tmp/test", "data_b64": "abc"}
    mock_conn.download_file.return_value = expected

    result = svc.download_file_from_node("lab-pi-01", "/tmp/test")

    assert result == expected
    mock_conn.download_file.assert_called_once_with("/tmp/test")


def test_download_file_from_node_disabled_node_returns_error():
    """download_file_from_node() returns node_disabled error for a disabled node."""
    from unittest.mock import MagicMock

    registry = NodeRegistry()
    cfg = NodeConfig(
        name="lab-pi-01",
        mode="direct",
        enabled=False,
        host="192.168.1.10",
        port=22,
        user="pi",
        id_file=None,
    )
    registry.add(cfg)

    pool = MagicMock()
    svc = NodeService(registry=registry, pool=pool, handshake_service=_make_noop_handshake(), agent_identity_service=MagicMock())

    result = svc.download_file_from_node("lab-pi-01", "/tmp/test")
    assert result == {"error": "node_disabled", "name": "lab-pi-01"}
