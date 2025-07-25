import logging
from mcp.server.fastmcp import FastMCP
from agent.connection_loader import ConnectionConfigError
import time
from agent import mcp_handlers

def run_agent():
    from agent.connection_loader import load_connections
    from agent.connection_pool import ConnectionPool
    import signal
    import sys

    logging.info("Initializing MCP agent...")

    # Load connection configuration
    try:
        connections = load_connections("connections.json")
    except (FileNotFoundError, ConnectionConfigError) as e:
        logging.error(f"❌ Configuration error: {e}")
        sys.exit(1)

    # Create and start the ConnectionPool
    pool = ConnectionPool(connections)
    pool.start_all()

    # Handle shutdown signals
    def shutdown_handler(sig, frame):
        logging.info("\n🔻 Received shutdown signal. Cleaning up...")
        pool.stop_all()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    # Initialize MCP Agent
    mcp = FastMCP(name="mcp-ssh-gateway")

    # Register supported MCP methods
    mcp.register("get_status", mcp_handlers.get_status)
    mcp.register("get_device_info", mcp_handlers.get_device_info)
    mcp.register("run_command", mcp_handlers.run_command)
    mcp.register("upload_file", mcp_handlers.upload_file)
    mcp.register("get_agent_pubkey", mcp_handlers.get_agent_pubkey)
    mcp.register("register_edge_key", mcp_handlers.register_edge_key)

    logging.info("Agent registered all handlers. Starting MCP loop.")
    mcp.run()

    # Keep the connection pool running
    logging.info("🔄 Connection pool is running. Press Ctrl+C to stop.")
    while True:
        time.sleep(1)
