"""
Focused wiring tests for agent/run_agent.py.

Scope: verify that run_agent constructs FastMCP with the stateless streamable-http
configuration intent (stateless_http=True, json_response=True) and that the
default transport/host/port in app.py match the expected dev-loop defaults.

These tests validate construction wiring and default parameter intent only.
They do not start a real listener, do not call MCP tools, and do not encode
exploratory Roo validation behavior as regression.
"""

import sys
from unittest.mock import MagicMock, patch


# ConnectionPool and load_and_parse_connections are imported inside run_agent()
# (not at module level), so they must be patched at their source locations.
_POOL_PATH = "agent.connectionpool.pool.ConnectionPool"
_CONFIG_LOADER_PATH = "agent.connectionpool.config_loader.load_and_parse_connections"


def _make_mock_mcp():
    """Return a mock FastMCP instance with the minimum attributes run_agent inspects."""
    mock = MagicMock()
    mock.settings = MagicMock(host="0.0.0.0", port=8000, log_level="INFO")
    return mock


def test_run_agent_constructs_fastmcp_with_stateless_http():
    """
    run_agent must construct FastMCP with stateless_http=True and json_response=True.
    These are the parameters that make the gateway survivable across restarts
    without requiring Roo to reset its MCP session.
    """
    mock_mcp_instance = _make_mock_mcp()
    mock_fastmcp_cls = MagicMock(return_value=mock_mcp_instance)

    with patch("agent.run_agent.FastMCP", mock_fastmcp_cls), \
         patch("agent.run_agent.mcp_handlers.register_tools"), \
         patch(_POOL_PATH, MagicMock(return_value=MagicMock())), \
         patch(_CONFIG_LOADER_PATH, return_value=[]), \
         patch("signal.signal"):

        from agent.run_agent import run_agent
        run_agent(config_path="", transport="streamable-http", host="0.0.0.0", port=8000)

    mock_fastmcp_cls.assert_called_once()
    _, kwargs = mock_fastmcp_cls.call_args
    assert kwargs.get("stateless_http") is True, (
        "FastMCP must be constructed with stateless_http=True to support restart-resilient "
        "Roo MCP validation without session-reset failures."
    )
    assert kwargs.get("json_response") is True, (
        "FastMCP must be constructed with json_response=True for Roo streamable-http "
        "client compatibility."
    )


def test_run_agent_passes_host_and_port_to_fastmcp():
    """
    run_agent must forward host and port arguments to the FastMCP constructor.
    """
    mock_mcp_instance = MagicMock()
    mock_mcp_instance.settings = MagicMock(host="127.0.0.1", port=9999, log_level="INFO")
    mock_fastmcp_cls = MagicMock(return_value=mock_mcp_instance)

    with patch("agent.run_agent.FastMCP", mock_fastmcp_cls), \
         patch("agent.run_agent.mcp_handlers.register_tools"), \
         patch(_POOL_PATH, MagicMock(return_value=MagicMock())), \
         patch(_CONFIG_LOADER_PATH, return_value=[]), \
         patch("signal.signal"):

        from agent.run_agent import run_agent
        run_agent(config_path="", transport="streamable-http", host="127.0.0.1", port=9999)

    _, kwargs = mock_fastmcp_cls.call_args
    assert kwargs.get("host") == "127.0.0.1"
    assert kwargs.get("port") == 9999


def test_run_agent_calls_mcp_run_with_transport():
    """
    run_agent must call mcp.run(transport=...) using the transport argument passed in.
    """
    mock_mcp_instance = _make_mock_mcp()
    mock_fastmcp_cls = MagicMock(return_value=mock_mcp_instance)

    with patch("agent.run_agent.FastMCP", mock_fastmcp_cls), \
         patch("agent.run_agent.mcp_handlers.register_tools"), \
         patch(_POOL_PATH, MagicMock(return_value=MagicMock())), \
         patch(_CONFIG_LOADER_PATH, return_value=[]), \
         patch("signal.signal"):

        from agent.run_agent import run_agent
        run_agent(config_path="", transport="streamable-http", host="0.0.0.0", port=8000)

    mock_mcp_instance.run.assert_called_once_with(transport="streamable-http")


def test_app_py_default_transport_is_streamable_http():
    """
    app.py argument parser must default to transport='streamable-http'.
    This is the canonical dev-loop transport. Changing the default is a breaking
    change for the Roo-assisted MCP validation loop.
    """
    saved_argv = sys.argv
    try:
        sys.argv = ["app.py"]
        import importlib
        import app as app_module
        importlib.reload(app_module)
        args = app_module.parse_args()
        assert args.transport == "streamable-http", (
            "Default transport in app.py must be 'streamable-http' for the dev loop."
        )
        assert args.host == "0.0.0.0"
        assert args.port == 8000
    finally:
        sys.argv = saved_argv
