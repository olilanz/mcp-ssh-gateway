#!/usr/bin/env python3

import argparse
import logging
from typing import Literal

def configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler()]
    )

from agent.run_agent import run_agent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MCP Agent")
    parser.add_argument(
        "--connection-config",
        type=str,
        default="",
        help="Path to the connection configuration file. Empty means no managed connections.",
    )
    parser.add_argument(
        "--transport",
        type=str,
        choices=["stdio", "sse", "streamable-http"],
        default="streamable-http",
        help="FastMCP transport to run.",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Listener host for network transports.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Listener port for network transports.",
    )
    return parser.parse_args()

if __name__ == "__main__":
    configure_logging()
    args = parse_args()

    transport = args.transport
    run_agent(
        config_path=args.connection_config,
        transport=transport,
        host=args.host,
        port=args.port,
    )
