import pytest
import subprocess
import time
import socket
import threading
from agent.connectionpool.connection import Connection


def test_direct_connection_success(spawn_sshd):
    sshd = spawn_sshd

    conn = Connection(
        name="test-direct",
        mode="direct",
        user=sshd.user,
        host="127.0.0.1",
        port=sshd.port,
        id_file=sshd.agent_id_file,
    )

    conn.open()
    result = conn.execute("echo hello")

    assert result.exit_code == 0
    assert result.stdout.strip() == "hello"
    assert result.stderr.strip() == ""


def test_direct_connection_key_mismatch(spawn_sshd, tmp_path):
    sshd = spawn_sshd

    # Generate a new identity key not in authorized_keys
    wrong_key = tmp_path / "wrong_id_rsa"
    subprocess.run(["ssh-keygen", "-t", "rsa", "-f", str(wrong_key), "-N", ""], check=True)

    conn = Connection(
        name="test-wrong-key",
        mode="direct",
        user=sshd.user,
        host="127.0.0.1",
        port=sshd.port,
        id_file=str(wrong_key),
    )

    conn.open()
    result = conn.execute("echo unreachable")

    assert result.exit_code != 0
    assert "Permission denied" in result.stderr or "Authentication failed" in result.stderr


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
            id_file=sshd.agent_id_file,
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
        "-i", sshd.agent_id_file,
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
        id_file=sshd.agent_id_file,
    )

    conn.open()
    result = conn.execute("echo tunnel")

    tunnel_proc.terminate()
    tunnel_proc.wait()

    assert result.exit_code == 0
    assert result.stdout.strip() == "tunnel"
    assert result.stderr.strip() == ""
