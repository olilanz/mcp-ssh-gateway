# agent/mcp_handlers.py

import os

def get_status():
    return {"status": "online", "mode": os.getenv("GATEWAY_MODE", "reverse")}

def register_edge_key(public_key: str, token: str):
    expected_token = os.getenv("PROVISION_TOKEN")
    if token != expected_token:
        raise PermissionError("Invalid provision token")

    with open("/keys/authorized_keys", "a") as f:
        f.write(public_key.strip() + "\n")

    return {"message": "Key registered"}

def get_agent_pubkey():
    with open("/keys/host_rsa.pub", "r") as f:
        return {"public_key": f.read().strip()}

def run_command(command: str):
    from .ssh_controller import exec_remote_command
    return exec_remote_command(command)

def upload_file(path: str, content: str):
    from .ssh_controller import upload_remote_file
    return upload_remote_file(path, content)

def get_device_info():
    from .ssh_controller import gather_device_info
    return gather_device_info()
