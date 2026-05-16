"""Unit tests for NodeService lifecycle mutation methods:
disable_node, enable_node, remove_node, add_node.
"""

import pytest

from agent.nodes.models import NodeConfig
from agent.nodes.registry import NodeRegistry
from agent.nodes.service import NodeService
from tests.agent.nodes.conftest import (
    make_node_config,
    make_mock_pool,
    make_service,
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
    """Returns {"error": "node not found", "name": ...} for unknown node."""
    svc = make_service()
    result = svc.enable_node("no-such-node")
    assert result == {"error": "node not found", "name": "no-such-node"}


def test_enable_node_validate_true_stubbed():
    """Returns validate_note field when validate=True."""
    svc = make_service(nodes=[("lab-pi-01", "direct", False)])
    result = svc.enable_node("lab-pi-01", validate=True)
    assert result["status"] == "enabled"
    assert result["name"] == "lab-pi-01"
    assert "validate_note" in result
    assert result["validate_note"] == "validation not yet implemented"


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
# NodeService — add_node() tests
# ---------------------------------------------------------------------------


def test_add_node_returns_bootstrap_not_implemented():
    """status == "bootstrap_not_implemented" and reason field is present."""
    registry = NodeRegistry()
    pool = make_mock_pool()
    svc = NodeService(registry=registry, pool=pool)
    result = svc.add_node(
        name="new-node",
        host="192.168.1.50",
        port=22,
        user="pi",
        password="some-password",
        mode="direct",
    )
    assert result["status"] == "bootstrap_not_implemented"
    assert "reason" in result
    assert result["name"] == "new-node"


def test_add_node_does_not_add_to_registry():
    """After add_node, node is NOT present in registry (registry.exists returns False)."""
    registry = NodeRegistry()
    pool = make_mock_pool()
    svc = NodeService(registry=registry, pool=pool)
    svc.add_node(
        name="new-node",
        host="192.168.1.50",
        port=22,
        user="pi",
        password="some-password",
        mode="direct",
    )
    assert registry.exists("new-node") is False


def test_add_node_result_has_no_password_field():
    """Return dict has no key 'password'."""
    registry = NodeRegistry()
    pool = make_mock_pool()
    svc = NodeService(registry=registry, pool=pool)
    result = svc.add_node(
        name="new-node",
        host="192.168.1.50",
        port=22,
        user="pi",
        password="some-password",
        mode="direct",
    )
    assert "password" not in result


def test_add_node_password_not_in_registry():
    """No password value appears in registry state after add_node call."""
    registry = NodeRegistry()
    pool = make_mock_pool()
    svc = NodeService(registry=registry, pool=pool)
    secret = "registry-safety-test-pw-99999"
    svc.add_node(
        name="new-node",
        host="192.168.1.50",
        port=22,
        user="pi",
        password=secret,
        mode="direct",
    )
    # Registry should have no entries (node was not added)
    assert registry.exists("new-node") is False
    # Double check: serialise all registry entries and confirm no secret
    for cfg, cache in registry.all():
        assert secret not in str(cfg)
        assert secret not in str(cache)


def test_add_node_password_not_in_logs(caplog):
    """Password string must not appear in any captured log record message."""
    import logging

    registry = NodeRegistry()
    pool = make_mock_pool()
    svc = NodeService(registry=registry, pool=pool)
    secret_password = "super-secret-bootstrap-pw-12345"
    with caplog.at_level(logging.DEBUG):
        result = svc.add_node(
            name="test-node",
            host="192.168.1.50",
            port=22,
            user="pi",
            password=secret_password,
            mode="direct",
        )
    # Password must not appear in any log record
    for record in caplog.records:
        assert secret_password not in record.getMessage(), (
            f"Password found in log record: {record.getMessage()}"
        )
    # Also verify not in return value
    assert secret_password not in str(result)
