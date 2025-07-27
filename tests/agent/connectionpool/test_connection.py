import sys
from pathlib import Path

# Add the workspace directory to the Python path
sys.path.append(str(Path(__file__).resolve().parents[3]))

from agent.connectionpool.connection import Connection

from unittest.mock import patch, MagicMock

@patch("paramiko.SSHClient")
def test_direct_connection(mock_ssh_client):
    class MockConfig:
        def __init__(self, name, user, id_file, mode, port, host):
            self.name = name
            self.user = user
            self.id_file = id_file
            self.mode = mode
            self.port = port
            self.host = host

    mock_ssh_instance = MagicMock()
    mock_ssh_client.return_value = mock_ssh_instance
    mock_ssh_instance.exec_command.return_value = (
        None,
        MagicMock(read=lambda: b"Hello, World!", channel=MagicMock(recv_exit_status=lambda: 0)),
        MagicMock(read=lambda: b"")
    )

    config = MockConfig(
        name="test_connection",
        user="testuser",
        id_file=None,
        mode="direct",
        port=22,
        host="localhost",
    )

    conn = Connection(config)
    conn.open()
    assert conn.get_state().name == "OPEN"

    result = conn.execute("echo 'Hello, World!'")
    assert result.command == "echo 'Hello, World!'"
    assert result.succeeded()
    assert "Hello, World!" in result.stdout

    conn.close()
    assert conn.get_state().name == "CLOSED"

    metadata = conn.describe()
    assert metadata["state"] == "closed"
    assert any("Hello, World!" in entry["stdout"] for entry in metadata["history"])