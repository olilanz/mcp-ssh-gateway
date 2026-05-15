"""
MCP handler-level tests for the get_agent_public_key tool.

Tests verify:
- Tool registration
- Correct fields returned (public_key, fingerprint, key_type)
- Private key material and paths are NOT returned

Uses a real FastMCP instance with a mocked AgentIdentityService.
Does NOT call real ssh-keygen.
Tool functions are invoked via the `.fn` attribute on the Tool object,
following the same pattern as tests/agent/test_mcp_node_tools.py.
"""

from unittest.mock import MagicMock
from mcp.server.fastmcp import FastMCP
from agent import mcp_handlers
from agent.identity.models import AgentIdentity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_test_mcp():
    """Return a fresh FastMCP instance for use in a single test."""
    return FastMCP(name="test-gateway")


def _make_mock_node_service():
    """Return a minimal MagicMock standing in for NodeService."""
    return MagicMock()


def _make_mock_identity_service():
    """Return a MagicMock standing in for AgentIdentityService with a fake identity."""
    svc = MagicMock()
    svc.get_identity.return_value = AgentIdentity(
        key_type="ed25519",
        public_key="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAtest test@gateway",
        fingerprint="SHA256:testfingerprint123",
        private_key_path="/tmp/fake/agent_id_ed25519",
        public_key_path="/tmp/fake/agent_id_ed25519.pub",
    )
    return svc


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

def test_get_agent_public_key_tool_is_registered():
    """get_agent_public_key must appear in the registered tool names."""
    mcp = _make_test_mcp()
    mcp_handlers.register_tools(mcp, _make_mock_node_service(), _make_mock_identity_service())

    assert "get_agent_public_key" in _tool_names(mcp), (
        f"Expected 'get_agent_public_key' in registered tools, got: {_tool_names(mcp)}"
    )


# ---------------------------------------------------------------------------
# Return value tests
# ---------------------------------------------------------------------------

def test_get_agent_public_key_returns_public_key():
    """Result dict must contain the 'public_key' field."""
    mcp = _make_test_mcp()
    mcp_handlers.register_tools(mcp, _make_mock_node_service(), _make_mock_identity_service())

    fn = _get_tool_fn(mcp, "get_agent_public_key")
    result = fn()

    assert "public_key" in result, f"Expected 'public_key' in result, got keys: {list(result.keys())}"
    assert result["public_key"] == "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAtest test@gateway"


def test_get_agent_public_key_returns_fingerprint():
    """Result dict must contain the 'fingerprint' field."""
    mcp = _make_test_mcp()
    mcp_handlers.register_tools(mcp, _make_mock_node_service(), _make_mock_identity_service())

    fn = _get_tool_fn(mcp, "get_agent_public_key")
    result = fn()

    assert "fingerprint" in result, f"Expected 'fingerprint' in result, got keys: {list(result.keys())}"
    assert result["fingerprint"] == "SHA256:testfingerprint123"


def test_get_agent_public_key_returns_key_type():
    """Result dict must contain the 'key_type' field."""
    mcp = _make_test_mcp()
    mcp_handlers.register_tools(mcp, _make_mock_node_service(), _make_mock_identity_service())

    fn = _get_tool_fn(mcp, "get_agent_public_key")
    result = fn()

    assert "key_type" in result, f"Expected 'key_type' in result, got keys: {list(result.keys())}"


# ---------------------------------------------------------------------------
# Security / non-disclosure tests
# ---------------------------------------------------------------------------

def test_get_agent_public_key_does_not_return_private_key():
    """Result must NOT contain a key named 'private_key'."""
    mcp = _make_test_mcp()
    mcp_handlers.register_tools(mcp, _make_mock_node_service(), _make_mock_identity_service())

    fn = _get_tool_fn(mcp, "get_agent_public_key")
    result = fn()

    assert "private_key" not in result, (
        "Handler must never expose private key material — 'private_key' must be absent from result"
    )


def test_get_agent_public_key_does_not_return_paths():
    """Result must NOT contain 'private_key_path', 'public_key_path', or 'key_dir'."""
    mcp = _make_test_mcp()
    mcp_handlers.register_tools(mcp, _make_mock_node_service(), _make_mock_identity_service())

    fn = _get_tool_fn(mcp, "get_agent_public_key")
    result = fn()

    for forbidden in ("private_key_path", "public_key_path", "key_dir"):
        assert forbidden not in result, (
            f"Handler must not expose filesystem paths — '{forbidden}' must be absent from result"
        )


# ---------------------------------------------------------------------------
# Value correctness tests
# ---------------------------------------------------------------------------

def test_get_agent_public_key_key_type_is_ed25519():
    """result['key_type'] must equal 'ed25519' for the mock identity."""
    mcp = _make_test_mcp()
    mcp_handlers.register_tools(mcp, _make_mock_node_service(), _make_mock_identity_service())

    fn = _get_tool_fn(mcp, "get_agent_public_key")
    result = fn()

    assert result["key_type"] == "ed25519", (
        f"Expected key_type='ed25519', got: {result['key_type']!r}"
    )
