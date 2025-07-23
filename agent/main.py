# agent/main.py

import sys
import json
from agent import mcp_handlers

def handle_mcp_request(raw_line):
    try:
        request = json.loads(raw_line)
        method = request.get("method")
        params = request.get("params", {})
        id_ = request.get("id")

        if not method:
            raise ValueError("Missing 'method' field")

        if hasattr(mcp_handlerss, method):
            result = getattr(mcp_handlerss, method)(**params)
            response = {"jsonrpc": "2.0", "result": result, "id": id_}
        else:
            response = {"jsonrpc": "2.0", "error": {"code": -32601, "message": "Method not found"}, "id": id_}

    except Exception as e:
        response = {"jsonrpc": "2.0", "error": {"code": -32000, "message": str(e)}, "id": None}

    print(json.dumps(response), flush=True)

def main():
    import threading
    from agent.ssh_controller import get_ssh_client

    def monitor_ssh_connection():
        import socket
        import time
        from agent.ssh_controller import get_ssh_client

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

    threading.Thread(target=monitor_ssh_connection, daemon=True).start()

    for line in sys.stdin:
        if line.strip():
            handle_mcp_request(line.strip())

if __name__ == '__main__':
    main()
