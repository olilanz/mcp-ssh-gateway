import logging
import threading
from mcp.server.fastmcp import FastMCP
from agent.connectionpool.config_loader import ConnectionConfigError
import time
import os
from agent import mcp_handlers

def run_agent(config_path="connections.json"):
    from agent.connectionpool.config_loader import load_and_parse_connections
    from agent.connectionpool.pool import ConnectionPool
    import signal
    import sys

    logging.info("Initializing MCP agent...")

    try:
        connections = load_and_parse_connections(config_path)
    except (FileNotFoundError, ConnectionConfigError) as e:
        logging.error(f"❌ Configuration error: {e}")
        sys.exit(1)

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

    # Start MCP loop (blocking)
    from agent import mcp_handlers
    mcp = FastMCP(name="mcp-ssh-gateway")
    mcp_handlers.register_tools(mcp)
    logging.info("Agent registered all handlers. MCP loop initiated.")
    mcp.run(transport="stdio")
