"""
MCP handler-level tests for node management tools.

Tests verify:
- Tool registration (which tools are registered / absent)
- Basic response shape from handler invocations
- Handler argument style consistency

Uses a real FastMCP instance with a mocked NodeService.
Tool registration is inspected via mcp._tool_manager.list_tools(),
which returns Tool objects with a `.name` attribute.
Tool functions are invoked via the `.fn` attribute on the Tool object.
"""

from unittest.mock import MagicMock
from mcp.server.fastmcp import FastMCP
from agent import mcp_handlers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_test_mcp():
    """Return a fresh FastMCP instance for use in a single test."""
    return FastMCP(name="test-gateway")


def make_mock_node_service():
    """Return a MagicMock standing in for NodeService with plausible return values."""
    svc = MagicMock()
    svc.get_node_status.return_value = {"status": "ok", "nodes": []}
    svc.get_node_info.return_value = {"nodes": []}
    svc.add_node.return_value = {"status": "bootstrap_not_implemented", "name": "test", "reason": "..."}
    svc.remove_node.return_value = {"status": "removed", "name": "test"}
    svc.enable_node.return_value = {"status": "enabled", "name": "test"}
    svc.disable_node.return_value = {"status": "disabled", "name": "test"}
    return svc


def make_mock_identity_service():
    """Return a MagicMock standing in for AgentIdentityService."""
    return MagicMock()


def _tool_names(mcp: FastMCP) -> list:
    """Return list of registered tool names from a FastMCP instance."""
    return [t.name for t in mcp._tool_manager.list_tools()]


def _get_tool_fn(mcp: FastMCP, name: str):
    """Return the inner function for a registered tool by name."""
    for t in mcp._tool_manager.list_tools():
        if t.name == name:
            return t.fn
    raise KeyError(f"Tool '{name}' not found in registered tools")


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------

def test_tool_registration_includes_all_six_node_tools():
    """All 6 node management tools must be registered."""
    mcp = make_test_mcp()
    svc = make_mock_node_service()
    mcp_handlers.register_tools(mcp, svc, make_mock_identity_service())

    names = _tool_names(mcp)
    for expected in ["get_node_status", "get_node_info", "add_node", "remove_node", "enable_node", "disable_node"]:
        assert expected in names, f"Expected tool '{expected}' to be registered, got: {names}"


def test_get_device_info_not_registered():
    """get_device_info must NOT be registered (retired in this slice)."""
    mcp = make_test_mcp()
    svc = make_mock_node_service()
    mcp_handlers.register_tools(mcp, svc, make_mock_identity_service())

    names = _tool_names(mcp)
    assert "get_device_info" not in names, (
        "get_device_info must be absent — it uses prohibited 'device' noun and is retired"
    )


def test_get_status_not_registered():
    """get_status must NOT be registered (renamed to get_node_status in this slice)."""
    mcp = make_test_mcp()
    svc = make_mock_node_service()
    mcp_handlers.register_tools(mcp, svc, make_mock_identity_service())

    names = _tool_names(mcp)
    assert "get_status" not in names, (
        "get_status must be absent — it has been renamed to get_node_status"
    )


def test_run_command_tool_not_registered():
    """Legacy local run_command must not appear in registered MCP tools."""
    mcp = make_test_mcp()
    svc = make_mock_node_service()
    mcp_handlers.register_tools(mcp, svc, make_mock_identity_service())

    assert "run_command" not in _tool_names(mcp), (
        "run_command must be absent — it executes commands on the gateway container itself, "
        "not on a managed node, and is a security footgun"
    )


def test_upload_file_tool_not_registered():
    """Legacy local upload_file must not appear in registered MCP tools."""
    mcp = make_test_mcp()
    svc = make_mock_node_service()
    mcp_handlers.register_tools(mcp, svc, make_mock_identity_service())

    assert "upload_file" not in _tool_names(mcp), (
        "upload_file must be absent — it writes files on the gateway container itself, "
        "not on a managed node, and is a security footgun"
    )


# ---------------------------------------------------------------------------
# Delegation tests
# ---------------------------------------------------------------------------

def test_get_node_status_delegates_to_service():
    """get_node_status handler must delegate to node_service.get_node_status() and return its result."""
    mcp = make_test_mcp()
    svc = make_mock_node_service()
    mcp_handlers.register_tools(mcp, svc, make_mock_identity_service())

    fn = _get_tool_fn(mcp, "get_node_status")
    result = fn()

    svc.get_node_status.assert_called_once_with()
    assert result == {"status": "ok", "nodes": []}


def test_get_node_info_delegates_to_service():
    """get_node_info handler must call node_service.get_node_info() with name and refresh."""
    mcp = make_test_mcp()
    svc = make_mock_node_service()
    mcp_handlers.register_tools(mcp, svc, make_mock_identity_service())

    fn = _get_tool_fn(mcp, "get_node_info")
    result = fn(name="node-a", refresh=True)

    svc.get_node_info.assert_called_once_with(name="node-a", refresh=True)
    assert result == {"nodes": []}


def test_add_node_delegates_to_service():
    """add_node handler must call node_service.add_node() with all required arguments."""
    mcp = make_test_mcp()
    svc = make_mock_node_service()
    mcp_handlers.register_tools(mcp, svc, make_mock_identity_service())

    fn = _get_tool_fn(mcp, "add_node")
    result = fn(name="node-b", host="192.168.1.5", port=22, username="pi", password="secret", mode="direct")

    svc.add_node.assert_called_once_with(
        name="node-b", host="192.168.1.5", port=22, username="pi", password="secret", mode="direct"
    )
    assert result["name"] == "test"


def test_remove_node_delegates_to_service():
    """remove_node handler must call node_service.remove_node() with name."""
    mcp = make_test_mcp()
    svc = make_mock_node_service()
    mcp_handlers.register_tools(mcp, svc, make_mock_identity_service())

    fn = _get_tool_fn(mcp, "remove_node")
    result = fn(name="node-c")

    svc.remove_node.assert_called_once_with(name="node-c")
    assert result == {"status": "removed", "name": "test"}


def test_enable_node_delegates_to_service():
    """enable_node handler must call node_service.enable_node() with name and validate."""
    mcp = make_test_mcp()
    svc = make_mock_node_service()
    mcp_handlers.register_tools(mcp, svc, make_mock_identity_service())

    fn = _get_tool_fn(mcp, "enable_node")
    result = fn(name="node-d", validate=True)

    svc.enable_node.assert_called_once_with(name="node-d", validate=True)
    assert result == {"status": "enabled", "name": "test"}


def test_disable_node_delegates_to_service():
    """disable_node handler must call node_service.disable_node() with name."""
    mcp = make_test_mcp()
    svc = make_mock_node_service()
    mcp_handlers.register_tools(mcp, svc, make_mock_identity_service())

    fn = _get_tool_fn(mcp, "disable_node")
    result = fn(name="node-e")

    svc.disable_node.assert_called_once_with(name="node-e")
    assert result == {"status": "disabled", "name": "test"}


# ---------------------------------------------------------------------------
# Signature test
# ---------------------------------------------------------------------------

def test_register_tools_signature_accepts_node_service():
    """register_tools(mcp, node_service, agent_identity_service) must not raise."""
    mcp = make_test_mcp()
    svc = make_mock_node_service()
    mcp_handlers.register_tools(mcp, svc, make_mock_identity_service())


# ---------------------------------------------------------------------------
# Handler tests — run_command_on_node / upload_file_to_node / download_file_from_node
# ---------------------------------------------------------------------------

def test_run_command_on_node_handler_delegates():
    """run_command_on_node handler must delegate to node_service.run_command_on_node() and return its result."""
    mcp = make_test_mcp()
    svc = make_mock_node_service()
    svc.run_command_on_node.return_value = {
        "exit_code": 0,
        "stdout": "hello",
        "stderr": "",
        "command": "echo hello",
        "started_at": "...",
        "ended_at": "...",
    }
    mcp_handlers.register_tools(mcp, svc, make_mock_identity_service())

    fn = _get_tool_fn(mcp, "run_command_on_node")
    result = fn(name="test-node", command="echo hello", timeout=30)

    svc.run_command_on_node.assert_called_once_with(name="test-node", command="echo hello", timeout=30)
    assert result == {
        "exit_code": 0,
        "stdout": "hello",
        "stderr": "",
        "command": "echo hello",
        "started_at": "...",
        "ended_at": "...",
    }


def test_upload_file_to_node_handler_delegates():
    """upload_file_to_node handler must delegate to node_service.upload_file_to_node() and return its result."""
    mcp = make_test_mcp()
    svc = make_mock_node_service()
    svc.upload_file_to_node.return_value = {"status": "written", "path": "/tmp/test.txt"}
    mcp_handlers.register_tools(mcp, svc, make_mock_identity_service())

    fn = _get_tool_fn(mcp, "upload_file_to_node")
    result = fn(name="test-node", remote_path="/tmp/test.txt", data_b64="aGVsbG8=", mode="0644")

    svc.upload_file_to_node.assert_called_once_with(
        name="test-node", remote_path="/tmp/test.txt", data_b64="aGVsbG8=", mode="0644"
    )
    assert result == {"status": "written", "path": "/tmp/test.txt"}


def test_download_file_from_node_handler_delegates():
    """download_file_from_node handler must delegate to node_service.download_file_from_node() and return its result."""
    mcp = make_test_mcp()
    svc = make_mock_node_service()
    svc.download_file_from_node.return_value = {"status": "ok", "path": "/tmp/test.txt", "data_b64": "aGVsbG8="}
    mcp_handlers.register_tools(mcp, svc, make_mock_identity_service())

    fn = _get_tool_fn(mcp, "download_file_from_node")
    result = fn(name="test-node", remote_path="/tmp/test.txt")

    svc.download_file_from_node.assert_called_once_with(name="test-node", remote_path="/tmp/test.txt")
    assert result == {"status": "ok", "path": "/tmp/test.txt", "data_b64": "aGVsbG8="}
