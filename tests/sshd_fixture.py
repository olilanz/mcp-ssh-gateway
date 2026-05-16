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


@dataclass
class SpawnedSSHDPassword:
    host: str             # always "127.0.0.1"
    port: int             # random high port
    username: str         # the sshbootstrap test user
    password: str         # the sshbootstrap test password
    host_key_path: str    # path to the sshd host key for this fixture instance
    process: subprocess.Popen


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

        # Start sshd in foreground (-D) with our config.
        # stdout/stderr go to DEVNULL since all logging is sent to log_path via -E.
        # Using PIPE would leave unclosed file descriptors that trigger ResourceWarning.
        process = subprocess.Popen(
            [sshd_bin, "-D", "-f", sshd_config_path, "-E", log_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
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


@pytest.fixture
def spawn_sshd_password(tmp_path):
    """Spawn an isolated local sshd allowing password auth for sshbootstrap user only.

    Uses a dedicated test-only Unix user (sshbootstrap) with a known password.
    Never mutates the vscode user. Never depends on system sshd.
    Skips if sshd is unavailable or sshbootstrap user does not exist.
    """
    import shutil as _shutil

    if _shutil.which("sshd") is None:
        pytest.skip("sshd not available in this environment")

    try:
        bootstrap_user = pwd.getpwnam("sshbootstrap")
    except KeyError:
        pytest.skip("sshbootstrap test user not available (add to Dockerfile)")

    sshd_bin = _shutil.which("sshd") or "/usr/sbin/sshd"

    # Generate host key for this fixture's sshd instance
    host_key_path = tmp_path / "host_key"
    subprocess.run(
        ["ssh-keygen", "-t", "rsa", "-b", "2048", "-N", "", "-f", str(host_key_path)],
        check=True, capture_output=True
    )

    # authorized_keys path for cleanup
    from pathlib import Path
    auth_keys_path = Path(bootstrap_user.pw_dir) / ".ssh" / "authorized_keys"

    # Clean authorized_keys before test
    auth_keys_path.parent.mkdir(mode=0o700, exist_ok=True)
    auth_keys_path.write_text("")
    auth_keys_path.chmod(0o600)

    # Find sftp-server
    sftp_server = "/usr/lib/openssh/sftp-server"
    if not os.path.exists(sftp_server):
        sftp_server = "/usr/lib/sftp-server"

    # sshd_config for this fixture
    port = _find_free_port()
    sshd_config_path = tmp_path / "sshd_config"
    pid_file = tmp_path / "sshd.pid"
    sshd_config_path.write_text(f"""
Port {port}
ListenAddress 127.0.0.1
HostKey {host_key_path}
PidFile {pid_file}
LogLevel DEBUG
AllowUsers sshbootstrap
PasswordAuthentication yes
PubkeyAuthentication yes
AuthorizedKeysFile {auth_keys_path}
PermitRootLogin no
UsePAM yes
StrictModes no
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no
Subsystem sftp {sftp_server}
""")

    log_path = tmp_path / "sshd.log"

    # Start sshd
    process = subprocess.Popen(
        [sshd_bin, "-D", "-f", str(sshd_config_path), "-E", str(log_path)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    try:
        try:
            _wait_for_port("127.0.0.1", port, timeout=10.0)
        except TimeoutError:
            process.terminate()
            process.wait()
            try:
                log_content = log_path.read_text()
            except Exception:
                log_content = "(no log)"
            pytest.skip(f"sshd (password fixture) failed to start on port {port}. Log:\n{log_content}")

        yield SpawnedSSHDPassword(
            host="127.0.0.1",
            port=port,
            username="sshbootstrap",
            password="sshbootstrap",
            host_key_path=str(host_key_path),
            process=process,
        )
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        # Clean up authorized_keys after test
        try:
            auth_keys_path.write_text("")
        except Exception:
            pass
