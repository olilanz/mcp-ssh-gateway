# agent/ssh_controller.py

import paramiko
import os

EDGE_HOST = "localhost"
EDGE_PORT = 2222
EDGE_USER = "root"
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def get_ssh_client():
    try:
        key = paramiko.RSAKey.from_private_key_file("/keys/host_rsa")
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(EDGE_HOST, EDGE_PORT, username=EDGE_USER, pkey=key)
        logging.info("SSH client connected successfully.")
        return client
    except Exception as e:
        logging.error(f"Failed to establish SSH connection: {e}")
        logging.debug("Retrying SSH connection in 5 seconds...")
        time.sleep(5)
        raise

def exec_remote_command(cmd):
    try:
        client = get_ssh_client()
        stdin, stdout, stderr = client.exec_command(cmd)
        result = {
            "stdout": stdout.read().decode(),
            "stderr": stderr.read().decode(),
            "exit_code": stdout.channel.recv_exit_status()
        }
        logging.info(f"Command executed: {cmd}")
        logging.debug(f"Command output: {result}")
        return result
    except Exception as e:
        logging.error(f"Error executing command '{cmd}': {e}")
        logging.debug(f"Command '{cmd}' failed with error: {e}")
        raise
    finally:
        client.close()

def upload_remote_file(path, content):
    try:
        client = get_ssh_client()
        sftp = client.open_sftp()
        with sftp.file(path, "w") as f:
            f.write(content)
        logging.info(f"File uploaded to {path}")
        return {"uploaded_to": path}
    except Exception as e:
        logging.error(f"Error uploading file to {path}: {e}")
        logging.debug(f"File upload to {path} failed with error: {e}")
        raise
    finally:
        sftp.close()
        client.close()

def gather_device_info():
    return exec_remote_command("sh /app/scripts/probe.sh")
