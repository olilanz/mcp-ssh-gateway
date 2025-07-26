import logging
from mcp.server.fastmcp import FastMCP
from agent.connectionpool.errors import ConnectionConfigError
import time
from agent import mcp_handlers

def run_agent(config_path="connections.json"):
    from agent.connectionpool.loader import load_connections
    from agent.connectionpool.pool import ConnectionPool
    import signal
    import sys

    logging.info("Initializing MCP agent...")

    # Load connection configuration
    try:
        connections = load_connections(config_path)
    except (FileNotFoundError, ConnectionConfigError) as e:
        logging.error(f"❌ Configuration error: {e}")
        sys.exit(1)

    # Create and start the ConnectionPool
    pool = ConnectionPool(connections)
    pool.start_all()

    # Query the connection pool state and log it
    pool_state = pool.query_pool()
    logging.info(f"🔍 Initial connection pool state: {pool_state}")

    # Handle shutdown signals
    def shutdown_handler(sig, frame):
        logging.info("\n🔻 Received shutdown signal. Cleaning up...")
        pool.stop_all()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    # Initialize MCP Agent
    mcp = FastMCP(name="mcp-ssh-gateway")
    mcp_handlers.register_tools(mcp)

    logging.info("Agent registered all handlers. Starting MCP loop.")
    mcp.run()

    # Keep the connection pool running
    logging.info("🔄 Connection pool is running. Press Ctrl+C to stop.")
    while True:
        time.sleep(1)
