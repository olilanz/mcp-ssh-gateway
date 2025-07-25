#!/usr/bin/env python3

import logging

from agent.connection_loader import load_connections, ConnectionConfigError
from agent.connection_pool import ConnectionPool


def configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler()]
    )

from agent.run_agent import run_agent

if __name__ == "__main__":
    configure_logging()
    run_agent()

