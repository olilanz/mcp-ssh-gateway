# agent/ssh_controller.py

import paramiko
import os

EDGE_HOST = "localhost"
EDGE_PORT = 2222
EDGE_USER = "root"

def get_ssh_client():
    key = paramiko.RSAKey.from_private_key_file("/keys/host_rsa")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(EDGE_HOST, EDGE_PORT, username=EDGE_USER, pkey=key)
    return client

def exec_remote_command(cmd):
    client = get_ssh_client()
    stdin, stdout, stderr = client.exec_command(cmd)
    result = {
        "stdout": stdout.read().decode(),
        "stderr": stderr.read().decode(),
        "exit_code": stdout.channel.recv_exit_status()
    }
    client.close()
    return result

def upload_remote_file(path, content):
    client = get_ssh_client()
    sftp = client.open_sftp()
    with sftp.file(path, "w") as f:
        f.write(content)
    sftp.close()
    client.close()
    return {"uploaded_to": path}

def gather_device_info():
    return exec_remote_command("sh /app/scripts/probe.sh")
