import logging
import threading
from typing import Literal
from mcp.server.fastmcp import FastMCP
from agent.connectionpool.config_loader import ConnectionConfigError
import time
import os
from agent import mcp_handlers
from agent.nodes.models import NodeConfig, NodeInfoCache
from agent.nodes.registry import NodeRegistry
from agent.nodes.service import NodeService

def run_agent(
    config_path="connections.json",
    transport: Literal["stdio", "sse", "streamable-http"] = "stdio",
    host="127.0.0.1",
    port=8000,
):
    from agent.connectionpool.config_loader import load_and_parse_connections
    from agent.connectionpool.pool import ConnectionPool
    import signal
    import sys

    logging.info("Initializing MCP agent...")

    if config_path:
        try:
            connections = load_and_parse_connections(config_path)
        except (FileNotFoundError, ConnectionConfigError) as e:
            logging.error(f"❌ Configuration error: {e}")
            sys.exit(1)
    else:
        logging.warning("No connection configuration supplied. Starting with an empty pool.")
        connections = []

    pool = ConnectionPool(connections)

    def shutdown_handler(sig, frame):
        logging.info("\n🔻 Received shutdown signal. Cleaning up...")
        pool.stop()

        os._exit(0)

    # Register signal handlers early
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    pool.start()
    logging.info(f"🔍 Initial connection pool state: {pool.query_pool()}")

    # Seed NodeRegistry from pool connections
    registry = NodeRegistry()
    for conn in pool.connections:
        cfg = NodeConfig(
            name=conn.name,
            mode=conn.mode.value,
            enabled=True,
            host=conn.host,
            port=conn.port,
            user=conn.user,
            id_file=conn.id_file,
        )
        registry.add(cfg)

    node_service = NodeService(registry=registry, pool=pool)

    # Start MCP loop (blocking)
    mcp = FastMCP(name="mcp-ssh-gateway", host=host, port=port, stateless_http=True, json_response=True)
    settings_host = getattr(getattr(mcp, "settings", None), "host", None)
    settings_port = getattr(getattr(mcp, "settings", None), "port", None)
    settings_log_level = getattr(getattr(mcp, "settings", None), "log_level", None)
    mcp_handlers.register_tools(mcp, node_service)
    logging.info(
        "Agent registered all handlers. MCP loop initiated "
        f"(transport={transport}, host={host}, port={port})."
    )
    logging.info(
        "FastMCP effective settings before run "
        f"(transport={transport}, settings.host={settings_host}, "
        f"settings.port={settings_port}, settings.log_level={settings_log_level})."
    )
    mcp.run(transport=transport)
