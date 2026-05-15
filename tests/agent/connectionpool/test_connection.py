import pytest
import subprocess
import time
import socket
import threading
from agent.connectionpool.connection import Connection
from agent.connectionpool.config_loader import ConnectionConfig


@pytest.mark.functional
@pytest.mark.requires_sshd
def test_direct_connection_success(spawn_sshd):
    sshd = spawn_sshd

    conn = Connection(
        name="test-direct",
        mode="direct",
        user=sshd.user,
        host="127.0.0.1",
        port=sshd.port,
        id_file=sshd.client_key_path,
    )

    conn.open()
    result = conn.execute("echo hello")

    assert result.exit_code == 0
    assert result.stdout.strip() == "hello"
    assert result.stderr.strip() == ""


@pytest.mark.functional
@pytest.mark.requires_sshd
def test_direct_connection_key_mismatch(spawn_sshd, tmp_path):
    sshd = spawn_sshd

    # Generate a new identity key not in authorized_keys
    wrong_key = tmp_path / "wrong_ed25519"
    subprocess.run(["ssh-keygen", "-t", "ed25519", "-f", str(wrong_key), "-N", ""], check=True, capture_output=True)

    import paramiko
    conn = Connection(
        name="test-wrong-key",
        mode="direct",
        user=sshd.user,
        host="127.0.0.1",
        port=sshd.port,
        id_file=str(wrong_key),
    )

    # DirectConnection.open() raises AuthenticationException on key mismatch
    with pytest.raises(paramiko.AuthenticationException):
        conn.open()


@pytest.mark.functional
@pytest.mark.requires_sshd
def test_tunnel_connection_success(spawn_sshd, tmp_path):
    sshd = spawn_sshd

    def find_free_port():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    # Start the agent-side tunnel listener (via the Connection class)
    listener_port = find_free_port()

    def run_tunnel_listener():
        Connection(
            name="listener",
            mode="tunnel",
            user="dummy",
            host="127.0.0.1",
            port=listener_port,
            id_file=sshd.client_key_path,
        ).run()

    listener_thread = threading.Thread(target=run_tunnel_listener, daemon=True)
    listener_thread.start()

    time.sleep(0.5)  # give server time to start

    tunnel_port = find_free_port()

    # Simulate edge device initiating reverse tunnel
    tunnel_proc = subprocess.Popen([
        "ssh",
        "-N",
        "-o", "ExitOnForwardFailure=yes",
        "-i", sshd.client_key_path,
        "-R", f"{tunnel_port}:localhost:{sshd.port}",
        "127.0.0.1",
        "-p", str(listener_port)
    ])

    time.sleep(1.0)  # wait for tunnel to be active

    conn = Connection(
        name="test-tunnel",
        mode="tunnel",
        user=sshd.user,
        host="127.0.0.1",
        port=tunnel_port,
        id_file=sshd.client_key_path,
    )

    conn.open()
    result = conn.execute("echo tunnel")

    tunnel_proc.terminate()
    tunnel_proc.wait()

    assert result.exit_code == 0
    assert result.stdout.strip() == "tunnel"
    assert result.stderr.strip() == ""


def test_connection_constructor_accepts_config_and_kwargs():
    config = ConnectionConfig(
        name="ctor-config",
        mode="direct",
        user="u",
        host="127.0.0.1",
        port=22,
        id_file="/tmp/id_rsa",
    )

    from_config = Connection(config)
    from_kwargs = Connection(
        name="ctor-kwargs",
        mode="tunnel",
        user="u2",
        host="127.0.0.1",
        port=22222,
        id_file="/tmp/id_rsa_2",
    )

    assert from_config.name == "ctor-config"
    assert from_config.mode.value == "direct"
    assert from_kwargs.name == "ctor-kwargs"
    assert from_kwargs.mode.value == "tunnel"
