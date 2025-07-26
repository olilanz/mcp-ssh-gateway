#!/usr/bin/env python3

import logging

from agent.connectionpool.connection_loader import load_connections, ConnectionConfigError
from agent.connectionpool.connection_pool import ConnectionPool

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
        default="connections.json",
        help="Path to the connection configuration file (default: connections.json)"
    )
    args = parser.parse_args()

    # Pass the configuration file path to run_agent
    run_agent(config_path=args.connection_config)

