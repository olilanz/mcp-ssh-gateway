import logging

from mcp.agent import Agent

agent = Agent(name="mcp-ssh-gateway")

@agent.method("get_status")
def get_status(params):
    logging.debug("get_status called")
    return {"status": "ok"}

@agent.method("get_device_info")
def get_device_info(params):
    import platform
    logging.debug("get_device_info called")
    return {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine()
    }

@agent.method("run_command")
def run_command(params):
    import subprocess
    cmd = params.get("cmd")
    logging.debug(f"run_command called: {cmd}")
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        return {"stdout": result.stdout, "stderr": result.stderr, "exit_code": result.returncode}
    except subprocess.CalledProcessError as e:
        return {"stdout": e.stdout, "stderr": e.stderr, "exit_code": e.returncode}

def upload_file(path, data_b64, mode="0644"):
    import base64
    import os

    logging.debug(f"upload_file called for {path} with mode {mode}")
    decoded = base64.b64decode(data_b64)
    with open(path, "wb") as f:
        f.write(decoded)
    os.chmod(path, int(mode, 8))
    return {"status": "written", "path": path}

def get_agent_pubkey():
    key_path = "/data/keys/id_rsa.pub"
    try:
        with open(key_path, "r") as f:
            pubkey = f.read().strip()
        logging.debug("Agent public key loaded.")
        return {"public_key": pubkey}
    except Exception as e:
        logging.error(f"Failed to load public key: {e}")
        return {"error": str(e)}

def register_edge_key(key_data, filename="edge_authorized.pub"):
    path = f"/data/keys/{filename}"
    try:
        with open(path, "w") as f:
            f.write(key_data.strip() + "\n")
        logging.info(f"Edge public key saved to {path}")
        return {"status": "registered", "file": path}
    except Exception as e:
        logging.error(f"Failed to write edge key: {e}")
        return {"error": str(e)}
