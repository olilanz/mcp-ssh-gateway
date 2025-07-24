import socket
import time
from agent.ssh_controller import get_ssh_client

def monitor_ssh_connection():
    LISTENER_PORT = 2222  # Fixed port for reverse shell listener

    while True:
        try:
            # Check if the port is open and listening
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(5)
                result = sock.connect_ex(("localhost", LISTENER_PORT))
                if result == 0:
                    print(f"Listener detected on port {LISTENER_PORT}", flush=True)

                    # Establish SSH connection
                    client = get_ssh_client()
                    print("SSH connection established", flush=True)

                    # Route traffic (placeholder for actual routing logic)
                    print("Routing traffic between SSH and MCP", flush=True)

                    client.close()
                else:
                    print(f"No listener on port {LISTENER_PORT}", flush=True)
        except Exception as e:
            print(f"Error monitoring SSH connection: {e}", flush=True)
        time.sleep(5)