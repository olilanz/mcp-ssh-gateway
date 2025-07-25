#!/usr/bin/env python3

import argparse
import os
import sys
import logging
import signal
import time

from agent.connection_loader import load_connections, ConnectionConfigError
from agent.connection_pool import ConnectionPool

def parse_args():
    parser = argparse.ArgumentParser(description="MCP SSH Gateway Agent")
    parser.add_argument("--connection-config", type=str, default="connections.json", help="Path to connection config JSON (default: connections.json)")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    logging.debug("Arguments parsed successfully.")
    return parser.parse_args()

def configure_logging(debug_enabled: bool):
    log_level = logging.DEBUG if debug_enabled else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stderr)]
    )
    logging.debug("Logging configured for DEBUG level.")

def run_agent(config_path):
    try:
        connections = load_connections(config_path)
    except (FileNotFoundError, ConnectionConfigError) as e:
        logging.error(f"❌ Configuration error: {e}")
        sys.exit(1)

    pool = ConnectionPool(connections)
    pool.start_all()

    # Expose pool state
    def query_pool_state():
        state = pool.expose_pool_state()
        logging.info("Connection Pool State:")
        for connection in state:
            logging.info(connection)

    # Example usage of querying the pool state
    query_pool_state()

    # Keep the connection pool running
    logging.info("🔄 Connection pool is running. Press Ctrl+C to stop.")
    while True:
        time.sleep(1)

    # Graceful shutdown
    def shutdown_handler(sig, frame):
        logging.info("\n🔻 Received shutdown signal. Cleaning up...")
        pool.stop_all()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)
