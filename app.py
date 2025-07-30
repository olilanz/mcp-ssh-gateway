#!/usr/bin/env python3

import logging
import sys

from agent.connectionpool.config_loader import load_connections, ConnectionConfigError
from agent.connectionpool.pool import ConnectionPool

def configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler()]
    )

from agent.run_agent import run_agent

if __name__ == "__main__":
    import argparse

    configure_logging()

    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="MCP Agent")
    parser.add_argument(
        "--connection-config",
        type=str,
        default=None,
        help="Path to the connection configuration file (optional)"
    )
    
    args = parser.parse_args()
    
    if args.connection_config is None:
        logging.warning("No connection configuration file supplied. The connection pool will not maintain any connections.")
        connections = []
    else:
        try:
            connections = load_connections(args.connection_config)
        except ConnectionConfigError as e:
            logging.error(f"Failed to load connections: {e}")
            connections = []
    
    # Ensure args is defined before using it
    if args.connection_config is None:
        logging.warning("No connection configuration file supplied. The connection pool will not maintain any connections.")
        connections = []
    else:
        try:
            connections = load_connections(args.connection_config)
        except ConnectionConfigError as e:
            logging.error(f"Failed to load connections: {e}")
            connections = []
    
    # Pass the configuration file path to run_agent
    if args.connection_config is not None:
        run_agent(config_path=args.connection_config)
    else:
        logging.warning("No connection configuration file supplied. Passing an empty array of connections.")
        run_agent(config_path="")

