# agent/config.py

import os

def get_config():
    return {
        "mode": os.getenv("GATEWAY_MODE", "reverse"),
        "port": int(os.getenv("SSH_PORT", 2222)),
        "provision_token": os.getenv("PROVISION_TOKEN", "changeme")
    }
