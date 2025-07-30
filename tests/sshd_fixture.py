import subprocess
import tempfile
import os
import shutil
import socket
import time
import pytest

from pathlib import Path

class SpawnedSSHD:
    def __init__(self, port, user, process, tempdir, agent_id_file):
        self.port = port
        self.user = user
        self.process = process
        self.tempdir = tempdir
        self.agent_id_file = agent_id_file

    def stop(self):
        if self.process:
            self.process.terminate()
            self.process.wait()
        shutil.rmtree(self.tempdir, ignore_errors=True)


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def spawn_sshd():
    tempdir = tempfile.mkdtemp()
    user = "testuser"
    host_key = os.path.join(tempdir, "ssh_host_rsa_key")
    agent_key = os.path.join(tempdir, "agent_id_rsa")
    authorized_keys = os.path.join(tempdir, "authorized_keys")
    sshd_config = os.path.join(tempdir, "sshd_config")

    # Generate host key for sshd
    subprocess.run(["ssh-keygen", "-t", "rsa", "-f", host_key, "-N", ""], check=True)
    # Generate agent identity key
    subprocess.run(["ssh-keygen", "-t", "rsa", "-f", agent_key, "-N", ""], check=True)

    # Extract public key and write to authorized_keys
    with open(f"{agent_key}.pub") as pubkey_file:
        pubkey = pubkey_file.read()
    with open(authorized_keys, "w") as auth_file:
        auth_file.write(pubkey)

    # Find a free port
    port = find_free_port()

    # Write sshd config
    with open(sshd_config, "w") as cfg:
        cfg.write(f"""
Port {port}
ListenAddress 127.0.0.1
HostKey {host_key}
AuthorizedKeysFile {authorized_keys}
PidFile none
LogLevel VERBOSE
PasswordAuthentication no
PermitRootLogin no
ChallengeResponseAuthentication no
UsePAM no
Subsystem sftp internal-sftp
""")

    # Start sshd
    process = subprocess.Popen([
        "sshd", "-f", sshd_config, "-D", "-e"
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Give sshd time to start
    time.sleep(0.5)

    yield SpawnedSSHD(
        port=port,
        user=user,
        process=process,
        tempdir=tempdir,
        agent_id_file=agent_key
    )

    # Teardown
    if process:
        process.terminate()
        process.wait()
    shutil.rmtree(tempdir, ignore_errors=True)
