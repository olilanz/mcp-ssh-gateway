import argparse
import os
import sys
from agent.mcp_request_handler import handle_mcp_request
from agent.ssh_monitor import monitor_ssh_connection
import threading

def parse_arguments():
    parser = argparse.ArgumentParser(description="Agent startup program")
    parser.add_argument("--config", type=str, help="Path to configuration file")
    parser.add_argument("--env", type=str, help="Environment variables file")
    return parser.parse_args()

def load_config(config_path):
    if config_path and os.path.exists(config_path):
        with open(config_path, "r") as file:
            return {
                "mode": os.getenv("GATEWAY_MODE", "reverse"),
                "port": int(os.getenv("SSH_PORT", 2222)),
                "provision_token": os.getenv("PROVISION_TOKEN", "changeme")
            }
    return None


def main():
    args = parse_arguments()
    config = load_config(args.config) or {}

    listener_port = config.get("port", 2222)
    threading.Thread(target=monitor_ssh_connection, args=(listener_port,), daemon=True).start()

    for line in sys.stdin:
        if line.strip():
            handle_mcp_request(line.strip())

if __name__ == "__main__":
    main()