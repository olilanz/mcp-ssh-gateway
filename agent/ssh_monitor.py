import socket
import time
from agent.ssh_controller import get_ssh_client

def monitor_ssh_connection(listener_port):
    import logging
    logging.basicConfig(level=logging.INFO)

    while True:
        try:
            # Check if the port is open and listening
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(5)
                result = sock.connect_ex(("localhost", listener_port))
                if result == 0:
                    logging.info(f"Listener detected on port {listener_port}")

                    # Establish SSH connection
                    client = get_ssh_client()
                    logging.info("SSH connection established")

                    # Route traffic (placeholder for actual routing logic)
                    logging.info("Routing traffic between SSH and MCP")

                    client.close()
                else:
                    logging.info(f"No listener on port {listener_port}")
        except Exception as e:
            logging.error(f"Error monitoring SSH connection: {e}")
        time.sleep(5)