"""
Isolated local sshd fixture for functional SSH tests.

Spawns a dedicated sshd process using:
- A generated temporary sshd_config (never reads /etc/ssh/sshd_config)
- A generated temporary ed25519 host key
- A generated temporary ed25519 client keypair (throwaway per test, separate from agent identity)
- An absolute AuthorizedKeysFile path
- Binds only to 127.0.0.1 on a random high port
- Probe-based startup (no sleep)
- Cleans up all temporary files on teardown
"""
import os
import pwd
import shutil
import socket
import subprocess
import tempfile
import time
from dataclasses import dataclass
from shutil import which
import pytest


@dataclass
class SpawnedSSHD:
    host: str             # always "127.0.0.1"
    port: int             # random high port
    user: str             # current Unix user (pwd.getpwuid)
    client_key_path: str  # path to throwaway client private key
    process: subprocess.Popen
    tempdir: str

    def stop(self):
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(host: str, port: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(f"sshd did not listen on {host}:{port} within {timeout}s")


@pytest.fixture
def spawn_sshd():
    """Spawn an isolated local sshd process for functional SSH testing."""
    # Find sshd binary before creating tempdir
    sshd_bin = which("sshd") or "/usr/sbin/sshd"
    if not os.path.exists(sshd_bin) or not os.access(sshd_bin, os.X_OK):
        pytest.skip("sshd binary not available")

    tempdir = tempfile.mkdtemp(prefix="sshd_fixture_")
    process = None
    try:
        current_user = pwd.getpwuid(os.getuid()).pw_name
        port = _find_free_port()

        # Generate host key
        host_key_path = os.path.join(tempdir, "ssh_host_ed25519_key")
        subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-N", "", "-f", host_key_path],
            check=True, capture_output=True
        )

        # Generate throwaway client keypair
        client_key_path = os.path.join(tempdir, "client_ed25519")
        subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-N", "", "-f", client_key_path],
            check=True, capture_output=True
        )

        # Set up authorized_keys with absolute path
        authorized_keys_path = os.path.join(tempdir, "authorized_keys")
        with open(client_key_path + ".pub") as f:
            pub_key = f.read().strip()
        with open(authorized_keys_path, "w") as f:
            f.write(pub_key + "\n")
        os.chmod(authorized_keys_path, 0o600)
        os.chmod(client_key_path, 0o600)

        # Write sshd_config
        sshd_config_path = os.path.join(tempdir, "sshd_config")
        sftp_server = "/usr/lib/openssh/sftp-server"
        if not os.path.exists(sftp_server):
            sftp_server = "/usr/lib/sftp-server"

        with open(sshd_config_path, "w") as f:
            f.write(f"""Port {port}
ListenAddress 127.0.0.1
HostKey {host_key_path}
AuthorizedKeysFile {authorized_keys_path}
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
StrictModes no
PidFile none
LogLevel VERBOSE
UsePAM no
ChallengeResponseAuthentication no
Subsystem sftp {sftp_server}
""")

        log_path = os.path.join(tempdir, "sshd.log")

        # Start sshd in foreground (-D) with our config
        process = subprocess.Popen(
            [sshd_bin, "-D", "-f", sshd_config_path, "-E", log_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            _wait_for_port("127.0.0.1", port)
        except TimeoutError:
            process.terminate()
            process.wait()
            process = None
            # Try to read log for diagnostics
            try:
                with open(log_path) as lf:
                    log_content = lf.read()
            except Exception:
                log_content = "(no log)"
            raise RuntimeError(f"sshd failed to start on port {port}. Log:\n{log_content}")

        sshd = SpawnedSSHD(
            host="127.0.0.1",
            port=port,
            user=current_user,
            client_key_path=client_key_path,
            process=process,
            tempdir=tempdir,
        )

        yield sshd

        sshd.stop()
        process = None

    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        shutil.rmtree(tempdir, ignore_errors=True)
