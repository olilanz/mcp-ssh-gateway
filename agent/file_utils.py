import base64
import os
import logging

def write_file(path, content_b64, mode="0644"):
    logging.debug(f"write_file to {path} with mode {mode}")
    content = base64.b64decode(content_b64)
    with open(path, "wb") as f:
        f.write(content)
    os.chmod(path, int(mode, 8))
    return path

def read_file(path):
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        logging.error(f"Failed to read file {path}: {e}")
        return None
