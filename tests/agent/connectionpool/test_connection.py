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
    try:
        result = conn.execute("echo hello")

        assert result.exit_code == 0
        assert result.stdout.strip() == "hello"
        assert result.stderr.strip() == ""
    finally:
        conn.close()


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


@pytest.mark.skip(reason="Agent-side reverse tunnel listener lifecycle is not implemented")
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


# ---------------------------------------------------------------------------
# BaseConnection.execute() — timeout tests
# ---------------------------------------------------------------------------


def _make_direct_connection_with_mock_ssh():
    """Build a DirectConnection with a pre-injected mock SSHClient."""
    from unittest.mock import MagicMock
    from agent.connectionpool.connection import DirectConnection
    from agent.connectionpool.connection import ConnectionState

    config = ConnectionConfig(
        name="mock-conn",
        mode="direct",
        user="u",
        host="127.0.0.1",
        port=22,
        id_file="/tmp/id_rsa",
    )
    conn = DirectConnection(config)
    mock_ssh = MagicMock()
    conn._ssh = mock_ssh
    conn.state = ConnectionState.OPEN
    return conn, mock_ssh


def test_execute_with_timeout_completes_when_command_finishes_quickly():
    """execute(cmd, timeout=5) returns CommandResult when command completes before deadline."""
    from unittest.mock import MagicMock

    conn, mock_ssh = _make_direct_connection_with_mock_ssh()

    mock_stdin = MagicMock()
    mock_stdout = MagicMock()
    mock_stderr = MagicMock()
    mock_stdout.channel.recv_exit_status.return_value = 0
    mock_stdout.read.return_value = b"hello"
    mock_stderr.read.return_value = b""
    mock_ssh.exec_command.return_value = (mock_stdin, mock_stdout, mock_stderr)

    result = conn.execute("echo hello", timeout=5)

    mock_ssh.exec_command.assert_called_once_with("echo hello")
    assert result.exit_code == 0


def test_execute_raises_timeout_error_on_channel_timeout():
    """execute() raises TimeoutError when command does not complete within the deadline."""
    import threading
    from unittest.mock import MagicMock

    conn, mock_ssh = _make_direct_connection_with_mock_ssh()

    mock_stdin = MagicMock()
    mock_stdout = MagicMock()
    mock_stderr = MagicMock()

    # Make recv_exit_status block indefinitely so the thread join times out
    block_event = threading.Event()

    def _blocking_recv():
        block_event.wait()
        return 0

    mock_stdout.channel.recv_exit_status.side_effect = _blocking_recv
    mock_stdout.read.return_value = b""
    mock_stderr.read.return_value = b""
    mock_ssh.exec_command.return_value = (mock_stdin, mock_stdout, mock_stderr)

    with pytest.raises(TimeoutError):
        conn.execute("sleep 10", timeout=0.1)

    # Unblock the daemon thread so it can exit cleanly
    block_event.set()


# ---------------------------------------------------------------------------
# BaseConnection.upload_file() tests
# ---------------------------------------------------------------------------


def test_upload_file_uses_sftp_putfo():
    """upload_file() calls sftp.putfo() with correct bytes."""
    import base64
    from unittest.mock import MagicMock, call

    conn, mock_ssh = _make_direct_connection_with_mock_ssh()
    mock_sftp = MagicMock()
    mock_ssh.open_sftp.return_value = mock_sftp

    data = b"hello world"
    data_b64 = base64.b64encode(data).decode()
    result = conn.upload_file("/tmp/test.txt", data_b64, "0644")

    assert result == {"status": "written", "path": "/tmp/test.txt"}
    # Verify putfo was called — check the bytes content
    assert mock_sftp.putfo.called
    call_args = mock_sftp.putfo.call_args
    # First arg is BytesIO with correct data
    buf_arg = call_args[0][0]
    assert buf_arg.read() == data
    assert call_args[0][1] == "/tmp/test.txt"


def test_upload_file_closes_sftp_on_success():
    """upload_file() calls sftp.close() on success."""
    import base64
    from unittest.mock import MagicMock

    conn, mock_ssh = _make_direct_connection_with_mock_ssh()
    mock_sftp = MagicMock()
    mock_ssh.open_sftp.return_value = mock_sftp

    data_b64 = base64.b64encode(b"content").decode()
    conn.upload_file("/tmp/test.txt", data_b64)

    mock_sftp.close.assert_called_once()


def test_upload_file_closes_sftp_on_error():
    """upload_file() calls sftp.close() even when putfo raises."""
    import base64
    from unittest.mock import MagicMock

    conn, mock_ssh = _make_direct_connection_with_mock_ssh()
    mock_sftp = MagicMock()
    mock_sftp.putfo.side_effect = IOError("write failed")
    mock_ssh.open_sftp.return_value = mock_sftp

    data_b64 = base64.b64encode(b"content").decode()
    with pytest.raises(IOError):
        conn.upload_file("/tmp/test.txt", data_b64)

    mock_sftp.close.assert_called_once()


def test_upload_file_invalid_base64_returns_error():
    """upload_file() returns invalid_base64 error and does NOT open SFTP."""
    from unittest.mock import MagicMock

    conn, mock_ssh = _make_direct_connection_with_mock_ssh()

    result = conn.upload_file("/tmp/test.txt", "!!!not-valid-base64!!!")

    assert result["error"] == "invalid_base64"
    assert result["path"] == "/tmp/test.txt"
    mock_ssh.open_sftp.assert_not_called()


def test_upload_file_invalid_mode_returns_error():
    """upload_file() returns invalid_mode error and does NOT open SFTP."""
    import base64
    from unittest.mock import MagicMock

    conn, mock_ssh = _make_direct_connection_with_mock_ssh()

    data_b64 = base64.b64encode(b"content").decode()
    result = conn.upload_file("/tmp/test.txt", data_b64, mode="abc")

    assert result["error"] == "invalid_mode"
    assert result["path"] == "/tmp/test.txt"
    assert result["mode"] == "abc"
    mock_ssh.open_sftp.assert_not_called()


# ---------------------------------------------------------------------------
# BaseConnection.download_file() tests
# ---------------------------------------------------------------------------


def test_download_file_uses_sftp_getfo():
    """download_file() calls sftp.getfo() and result contains data_b64."""
    import base64
    from unittest.mock import MagicMock

    conn, mock_ssh = _make_direct_connection_with_mock_ssh()
    mock_sftp = MagicMock()
    mock_ssh.open_sftp.return_value = mock_sftp

    # stat returns a small file
    mock_stat = MagicMock()
    mock_stat.st_size = 100
    mock_sftp.stat.return_value = mock_stat

    # getfo writes bytes into buf
    original_data = b"file content here"

    def fake_getfo(path, buf):
        buf.write(original_data)

    mock_sftp.getfo.side_effect = fake_getfo

    result = conn.download_file("/tmp/test.txt")

    assert result["status"] == "ok"
    assert result["path"] == "/tmp/test.txt"
    assert "data_b64" in result
    assert base64.b64decode(result["data_b64"]) == original_data
    mock_sftp.getfo.assert_called_once()


def test_download_file_size_guard_stat_too_large():
    """download_file() returns file_too_large when stat reports >10MB."""
    from unittest.mock import MagicMock

    conn, mock_ssh = _make_direct_connection_with_mock_ssh()
    mock_sftp = MagicMock()
    mock_ssh.open_sftp.return_value = mock_sftp

    mock_stat = MagicMock()
    mock_stat.st_size = 20 * 1024 * 1024  # 20 MB
    mock_sftp.stat.return_value = mock_stat

    result = conn.download_file("/tmp/bigfile.bin")

    assert result["error"] == "file_too_large"
    assert result["path"] == "/tmp/bigfile.bin"
    assert result["size_bytes"] == 20 * 1024 * 1024
    assert result["limit_bytes"] == 10 * 1024 * 1024
    mock_sftp.getfo.assert_not_called()


def test_download_file_closes_sftp_on_success():
    """download_file() calls sftp.close() on success."""
    from unittest.mock import MagicMock

    conn, mock_ssh = _make_direct_connection_with_mock_ssh()
    mock_sftp = MagicMock()
    mock_ssh.open_sftp.return_value = mock_sftp

    mock_stat = MagicMock()
    mock_stat.st_size = 50
    mock_sftp.stat.return_value = mock_stat

    def fake_getfo(path, buf):
        buf.write(b"data")

    mock_sftp.getfo.side_effect = fake_getfo

    conn.download_file("/tmp/test.txt")

    mock_sftp.close.assert_called_once()


def test_download_file_not_found_returns_error():
    """download_file() returns file_not_found when getfo raises IOError."""
    from unittest.mock import MagicMock

    conn, mock_ssh = _make_direct_connection_with_mock_ssh()
    mock_sftp = MagicMock()
    mock_ssh.open_sftp.return_value = mock_sftp

    mock_stat = MagicMock()
    mock_stat.st_size = 50
    mock_sftp.stat.return_value = mock_stat
    mock_sftp.getfo.side_effect = IOError("No such file")

    result = conn.download_file("/tmp/missing.txt")

    assert result["error"] == "file_not_found"
    assert result["path"] == "/tmp/missing.txt"
    mock_sftp.close.assert_called_once()
