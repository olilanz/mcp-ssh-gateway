#!/usr/bin/env python3

import argparse
import os
import sys
import logging

from agent.main import run_agent

def parse_config():
    parser = argparse.ArgumentParser(description="MCP SSH Gateway Agent")

    parser.add_argument("--ssh-reverse-port", type=int, required=True, help="SSH listening port (e.g. 2222)")
    parser.add_argument("--key-dir", type=str, required=True, help="Directory containing RSA keys")
    parser.add_argument("--mode", choices=["reverse", "forward"], default="reverse", help="SSH connection mode")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")

    args = parser.parse_args()

    # Validation
    if args.ssh_reverse_port < 1 or args.ssh_reverse_port > 65535:
        print("Error: Invalid SSH reverse port number.")
        sys.exit(1)

    if not os.path.isdir(args.key_dir):
        print(f"Error: Key directory '{args.key_dir}' does not exist.")
        sys.exit(1)

    return args

def configure_logging(debug_enabled: bool):
    log_level = logging.DEBUG if debug_enabled else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    logging.debug("Logging configured for DEBUG level.")

def main():
    config = parse_config()
    configure_logging(config.debug)
    run_agent(config)

if __name__ == "__main__":
    main()
