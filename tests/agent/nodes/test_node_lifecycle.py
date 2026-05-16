"""Unit tests for NodeService lifecycle mutation methods:
disable_node, enable_node, remove_node, add_node.
"""

import pytest
from unittest.mock import MagicMock, patch, call

from agent.nodes.models import NodeConfig
from agent.nodes.registry import NodeRegistry
from agent.nodes.service import NodeService
from tests.agent.nodes.conftest import (
    make_node_config,
    make_mock_pool,
    make_service,
    make_mock_identity_service,
)


# ---------------------------------------------------------------------------
# NodeService — disable_node() tests
# ---------------------------------------------------------------------------


def test_disable_node_sets_enabled_false():
    """After disable_node, get_node_status shows enabled=False for that node."""
    svc = make_service(nodes=[("lab-pi-01", "direct", True)])
    svc.disable_node("lab-pi-01")
    result = svc.get_node_status()
    node = result["nodes"][0]
    assert node["name"] == "lab-pi-01"
    assert node["enabled"] is False


def test_disable_node_calls_pool_disable():
    """pool.disable_connection(name) is called when disable_node is invoked."""
    registry = NodeRegistry()
    registry.add(make_node_config("lab-pi-01"))
    pool = make_mock_pool()
    svc = NodeService(registry=registry, pool=pool)
    svc.disable_node("lab-pi-01")
    pool.disable_connection.assert_called_once_with("lab-pi-01")


def test_disable_node_node_still_visible_in_status():
    """Disabled node still appears in get_node_status result."""
    svc = make_service(nodes=[("lab-pi-01", "direct", True)])
    svc.disable_node("lab-pi-01")
    result = svc.get_node_status()
    names = [n["name"] for n in result["nodes"]]
    assert "lab-pi-01" in names


def test_disable_node_unknown_returns_error():
    """Returns {"error": "node not found", "name": ...} for unknown node."""
    svc = make_service()
    result = svc.disable_node("no-such-node")
    assert result == {"error": "node not found", "name": "no-such-node"}


# ---------------------------------------------------------------------------
# NodeService — enable_node() tests
# ---------------------------------------------------------------------------


def test_enable_node_sets_enabled_true():
    """After enable_node, get_node_status shows enabled=True for that node."""
    svc = make_service(nodes=[("lab-pi-01", "direct", False)])
    svc.enable_node("lab-pi-01")
    result = svc.get_node_status()
    node = result["nodes"][0]
    assert node["name"] == "lab-pi-01"
    assert node["enabled"] is True


def test_enable_node_calls_pool_enable():
    """pool.enable_connection(name) is called when enable_node is invoked."""
    registry = NodeRegistry()
    registry.add(make_node_config("lab-pi-01", enabled=False))
    pool = make_mock_pool()
    svc = NodeService(registry=registry, pool=pool)
    svc.enable_node("lab-pi-01")
    pool.enable_connection.assert_called_once_with("lab-pi-01")


def test_enable_node_unknown_returns_error():
    """Returns {"error": "not_found", "name": ...} for unknown node."""
    svc = make_service()
    result = svc.enable_node("no-such-node")
    assert result == {"error": "not_found", "name": "no-such-node"}


# ---------------------------------------------------------------------------
# NodeService — enable_node(validate=True) tests
# ---------------------------------------------------------------------------


def test_enable_validate_true_not_found():
    """enable_node(validate=True) for unknown node returns not_found error."""
    svc = make_service()
    result = svc.enable_node("unknown", validate=True)
    assert result == {"error": "not_found", "name": "unknown"}


def test_enable_validate_true_not_in_pool():
    """enable_node(validate=True) when pool.get_connection returns None → not_in_pool, node stays enabled."""
    from unittest.mock import MagicMock
    from agent.nodes.registry import NodeRegistry
    from agent.nodes.service import NodeService

    registry = NodeRegistry()
    registry.add(make_node_config("lab-pi-01", enabled=False))

    pool = make_mock_pool()
    pool.get_connection.return_value = None

    mock_handshake = MagicMock()
    svc = NodeService(registry=registry, pool=pool, handshake_service=mock_handshake)

    result = svc.enable_node("lab-pi-01", validate=True)

    assert result["status"] == "enabled"
    assert result["name"] == "lab-pi-01"
    assert result["validated"] is False
    assert result["error"] == "not_in_pool"
    # Node stays enabled despite probe failure
    cfg, _ = registry.get("lab-pi-01")
    assert cfg.enabled is True
    # Handshake never called
    mock_handshake.run.assert_not_called()


def test_enable_validate_true_connection_not_open():
    """enable_node(validate=True) when ensure_connection_open returns None → connection_not_open, node stays enabled."""
    from unittest.mock import MagicMock
    from agent.nodes.registry import NodeRegistry
    from agent.nodes.service import NodeService

    registry = NodeRegistry()
    registry.add(make_node_config("lab-pi-01", enabled=False))

    pool = make_mock_pool()
    pool.get_connection.return_value = MagicMock()  # connection exists in pool
    pool.ensure_connection_open.return_value = None  # but can't be opened

    mock_handshake = MagicMock()
    svc = NodeService(registry=registry, pool=pool, handshake_service=mock_handshake)

    result = svc.enable_node("lab-pi-01", validate=True)

    assert result["status"] == "enabled"
    assert result["name"] == "lab-pi-01"
    assert result["validated"] is False
    assert result["error"] == "connection_not_open"
    # Node stays enabled
    cfg, _ = registry.get("lab-pi-01")
    assert cfg.enabled is True
    # Handshake never called
    mock_handshake.run.assert_not_called()


def test_enable_validate_true_handshake_success():
    """enable_node(validate=True) when handshake succeeds → validated=True, cache updated."""
    from unittest.mock import MagicMock, call
    from agent.nodes.registry import NodeRegistry
    from agent.nodes.service import NodeService

    registry = NodeRegistry()
    registry.add(make_node_config("lab-pi-01", enabled=False))

    mock_conn = MagicMock()
    pool = make_mock_pool()
    pool.get_connection.return_value = mock_conn
    pool.ensure_connection_open.return_value = mock_conn

    facts = {"hostname": {"value": "pi", "source": "handshake", "collected_at": ""}}
    mock_handshake = MagicMock()
    mock_handshake.run.return_value = facts

    svc = NodeService(registry=registry, pool=pool, handshake_service=mock_handshake)

    result = svc.enable_node("lab-pi-01", validate=True)

    assert result == {"status": "enabled", "name": "lab-pi-01", "validated": True}
    # Handshake called with the open connection
    mock_handshake.run.assert_called_once_with(mock_conn, timeout=10)
    # Cache was updated in the registry
    _, cache = registry.get("lab-pi-01")
    assert cache.facts == facts


def test_enable_validate_true_handshake_failed():
    """enable_node(validate=True) when handshake returns {} → handshake_failed, node stays enabled."""
    from unittest.mock import MagicMock
    from agent.nodes.registry import NodeRegistry
    from agent.nodes.service import NodeService

    registry = NodeRegistry()
    registry.add(make_node_config("lab-pi-01", enabled=False))

    mock_conn = MagicMock()
    pool = make_mock_pool()
    pool.get_connection.return_value = mock_conn
    pool.ensure_connection_open.return_value = mock_conn

    mock_handshake = MagicMock()
    mock_handshake.run.return_value = {}  # handshake returns empty dict

    svc = NodeService(registry=registry, pool=pool, handshake_service=mock_handshake)

    result = svc.enable_node("lab-pi-01", validate=True)

    assert result["status"] == "enabled"
    assert result["name"] == "lab-pi-01"
    assert result["validated"] is False
    assert result["error"] == "handshake_failed"
    # Node stays enabled
    cfg, _ = registry.get("lab-pi-01")
    assert cfg.enabled is True


def test_enable_validate_false_does_not_probe():
    """enable_node(validate=False) never calls pool.get_connection or handshake_service.run."""
    from unittest.mock import MagicMock
    from agent.nodes.registry import NodeRegistry
    from agent.nodes.service import NodeService

    registry = NodeRegistry()
    registry.add(make_node_config("lab-pi-01", enabled=False))

    pool = make_mock_pool()
    mock_handshake = MagicMock()
    svc = NodeService(registry=registry, pool=pool, handshake_service=mock_handshake)

    result = svc.enable_node("lab-pi-01", validate=False)

    assert result == {"status": "enabled", "name": "lab-pi-01", "validated": False}
    pool.get_connection.assert_not_called()
    mock_handshake.run.assert_not_called()


# ---------------------------------------------------------------------------
# NodeService — remove_node() tests
# ---------------------------------------------------------------------------


def test_remove_node_removes_from_status():
    """After remove_node, node is absent from get_node_status."""
    svc = make_service(nodes=[("lab-pi-01", "direct", True)])
    svc.remove_node("lab-pi-01")
    result = svc.get_node_status()
    names = [n["name"] for n in result["nodes"]]
    assert "lab-pi-01" not in names


def test_remove_node_calls_pool_remove():
    """pool.remove_connection(name) is called when remove_node is invoked."""
    registry = NodeRegistry()
    registry.add(make_node_config("lab-pi-01"))
    pool = make_mock_pool()
    svc = NodeService(registry=registry, pool=pool)
    svc.remove_node("lab-pi-01")
    pool.remove_connection.assert_called_once_with("lab-pi-01")


def test_remove_node_unknown_returns_error():
    """Returns {"error": "node not found", "name": ...} for unknown node."""
    svc = make_service()
    result = svc.remove_node("no-such-node")
    assert result == {"error": "node not found", "name": "no-such-node"}


# ---------------------------------------------------------------------------
# NodeService — add_node() bootstrap tests (Phase 4)
# ---------------------------------------------------------------------------


# Shared helper for all bootstrap tests
_ADD_NODE_KWARGS = dict(
    name="new-node",
    host="192.168.1.50",
    port=22,
    username="pi",
    password="s3cr3t-bootstrap",
    mode="direct",
)


def test_add_node_unsupported_mode():
    """mode != 'direct' → {"error": "unsupported_mode"}, no SSH attempted."""
    registry = NodeRegistry()
    pool = make_mock_pool()
    svc = NodeService(registry=registry, pool=pool)

    with patch("paramiko.SSHClient") as mock_ssh_cls:
        result = svc.add_node(
            name="new-node",
            host="192.168.1.50",
            port=22,
            username="pi",
            password="s3cr3t",
            mode="tunnel",
        )

    assert result["error"] == "unsupported_mode"
    assert result["mode"] == "tunnel"
    assert "reason" in result
    # No SSH client created
    mock_ssh_cls.assert_not_called()
    # Registry untouched
    assert registry.exists("new-node") is False


def test_add_node_already_exists():
    """name already in registry → {"error": "already_exists"}, no SSH attempted."""
    registry = NodeRegistry()
    registry.add(make_node_config("new-node"))
    pool = make_mock_pool()
    svc = NodeService(registry=registry, pool=pool)

    with patch("paramiko.SSHClient") as mock_ssh_cls:
        result = svc.add_node(**_ADD_NODE_KWARGS)

    assert result == {"error": "already_exists", "name": "new-node"}
    mock_ssh_cls.assert_not_called()


def test_add_node_password_connect_failed():
    """pw_client.connect() raises → {"error": "password_connect_failed"}, registry unchanged, pw_client closed."""
    registry = NodeRegistry()
    pool = make_mock_pool()
    svc = NodeService(registry=registry, pool=pool)

    mock_pw_client = MagicMock()
    mock_pw_client.connect.side_effect = Exception("Connection refused")

    with patch("paramiko.SSHClient", return_value=mock_pw_client):
        result = svc.add_node(**_ADD_NODE_KWARGS)

    assert result["error"] == "password_connect_failed"
    assert result["name"] == "new-node"
    assert "detail" in result
    # pw_client must be closed even on failure
    mock_pw_client.close.assert_called()
    # Registry unchanged
    assert registry.exists("new-node") is False


def test_add_node_identity_not_available():
    """identity_service is None → {"error": "identity_not_available"}, pw_client closed."""
    registry = NodeRegistry()
    pool = make_mock_pool()
    # No identity service
    svc = NodeService(registry=registry, pool=pool, agent_identity_service=None)

    mock_pw_client = MagicMock()

    with patch("paramiko.SSHClient", return_value=mock_pw_client):
        result = svc.add_node(**_ADD_NODE_KWARGS)

    assert result == {"error": "identity_not_available", "name": "new-node"}
    mock_pw_client.close.assert_called()
    assert registry.exists("new-node") is False


def test_add_node_key_install_failed():
    """SFTP open_sftp raises → {"error": "key_install_failed"}, pw_client closed, registry unchanged."""
    registry = NodeRegistry()
    pool = make_mock_pool()
    identity_svc = make_mock_identity_service()
    svc = NodeService(registry=registry, pool=pool, agent_identity_service=identity_svc)

    mock_pw_client = MagicMock()
    mock_pw_client.open_sftp.side_effect = Exception("SFTP not available")

    with patch("paramiko.SSHClient", return_value=mock_pw_client):
        result = svc.add_node(**_ADD_NODE_KWARGS)

    assert result["error"] == "key_install_failed"
    assert result["name"] == "new-node"
    assert "detail" in result
    mock_pw_client.close.assert_called()
    assert registry.exists("new-node") is False


def test_add_node_key_auth_failed():
    """ensure_connection_open returns None → {"error": "key_auth_failed"}, pool.remove_connection called, registry unchanged."""
    registry = NodeRegistry()
    pool = make_mock_pool()
    # pool.add_connection must actually add to pool.connections for ensure_connection_open to work;
    # but since pool is a mock, we configure relevant methods
    pool.ensure_connection_open.return_value = None
    identity_svc = make_mock_identity_service()
    svc = NodeService(registry=registry, pool=pool, agent_identity_service=identity_svc)

    mock_pw_client = MagicMock()
    mock_sftp = MagicMock()
    mock_sftp.normalize.return_value = "/home/pi"
    mock_sftp.stat.side_effect = FileNotFoundError  # triggers mkdir
    mock_sftp.file.return_value.__enter__ = MagicMock(return_value=MagicMock(read=lambda: b""))
    mock_sftp.file.return_value.__exit__ = MagicMock(return_value=False)
    mock_pw_client.open_sftp.return_value = mock_sftp

    with patch("paramiko.SSHClient", return_value=mock_pw_client):
        result = svc.add_node(**_ADD_NODE_KWARGS)

    assert result == {"error": "key_auth_failed", "name": "new-node"}
    # Rollback: remove_connection called
    pool.remove_connection.assert_called_once_with("new-node")
    # Registry still clean
    assert registry.exists("new-node") is False


def test_add_node_success():
    """All steps succeed → {"status": "added", "validated": True}, registry.add called, pool entry exists."""
    registry = NodeRegistry()
    pool = make_mock_pool()
    mock_open_conn = MagicMock()
    pool.ensure_connection_open.return_value = mock_open_conn
    identity_svc = make_mock_identity_service()
    svc = NodeService(registry=registry, pool=pool, agent_identity_service=identity_svc)

    mock_pw_client = MagicMock()
    mock_sftp = MagicMock()
    mock_sftp.normalize.return_value = "/home/pi"
    mock_sftp.stat.side_effect = FileNotFoundError  # .ssh dir missing → mkdir
    # open returns a context-manager-like mock with read()
    mock_fh = MagicMock()
    mock_fh.read.return_value = b""
    mock_sftp.file.return_value.__enter__ = MagicMock(return_value=mock_fh)
    mock_sftp.file.return_value.__exit__ = MagicMock(return_value=False)
    mock_pw_client.open_sftp.return_value = mock_sftp

    with patch("paramiko.SSHClient", return_value=mock_pw_client):
        result = svc.add_node(**_ADD_NODE_KWARGS)

    assert result == {"status": "added", "name": "new-node", "validated": True}
    # Registry now contains the node
    assert registry.exists("new-node") is True
    cfg, _ = registry.get("new-node")
    assert cfg.name == "new-node"
    assert cfg.enabled is True
    # pool.add_connection was called
    pool.add_connection.assert_called_once()
    # pw_client closed (step 5)
    mock_pw_client.close.assert_called()


def test_add_node_password_never_in_config():
    """After successful add_node, the ConnectionConfig passed to pool has no password field."""
    registry = NodeRegistry()
    pool = make_mock_pool()
    mock_open_conn = MagicMock()
    pool.ensure_connection_open.return_value = mock_open_conn
    identity_svc = make_mock_identity_service()
    svc = NodeService(registry=registry, pool=pool, agent_identity_service=identity_svc)

    mock_pw_client = MagicMock()
    mock_sftp = MagicMock()
    mock_sftp.normalize.return_value = "/home/pi"
    mock_sftp.stat.side_effect = FileNotFoundError
    mock_fh = MagicMock()
    mock_fh.read.return_value = b""
    mock_sftp.file.return_value.__enter__ = MagicMock(return_value=mock_fh)
    mock_sftp.file.return_value.__exit__ = MagicMock(return_value=False)
    mock_pw_client.open_sftp.return_value = mock_sftp

    with patch("paramiko.SSHClient", return_value=mock_pw_client):
        result = svc.add_node(**_ADD_NODE_KWARGS)

    assert result["status"] == "added"
    # Inspect the ConnectionConfig passed to add_connection
    pool.add_connection.assert_called_once()
    config_arg = pool.add_connection.call_args[0][0]
    # No password field on ConnectionConfig
    assert not hasattr(config_arg, "password")
    assert "password" not in str(config_arg)
    # Confirm result dict also has no password
    assert "password" not in result


def test_add_node_password_not_in_logs(caplog):
    """Password must not appear in any captured log record regardless of outcome."""
    import logging

    registry = NodeRegistry()
    pool = make_mock_pool()
    svc = NodeService(registry=registry, pool=pool, agent_identity_service=None)
    secret_password = "super-secret-bootstrap-pw-12345"

    mock_pw_client = MagicMock()

    with patch("paramiko.SSHClient", return_value=mock_pw_client), \
         caplog.at_level(logging.DEBUG):
        result = svc.add_node(
            name="test-node",
            host="192.168.1.50",
            port=22,
            username="pi",
            password=secret_password,
            mode="direct",
        )

    for record in caplog.records:
        assert secret_password not in record.getMessage(), (
            f"Password found in log record: {record.getMessage()}"
        )
    assert secret_password not in str(result)
