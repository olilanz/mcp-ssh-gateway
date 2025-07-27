import pytest
import sys
from pathlib import Path

# Add the workspace directory to the Python path
sys.path.append(str(Path(__file__).resolve().parents[3]))

from agent.connectionpool.connection import Connection

def test_direct_connection(sshd_fixture):
    class MockConfig:
        def __init__(self, name, user, id_file, mode, port, host):
            self.name = name
            self.user = user
            self.id_file = id_file
            self.mode = mode
            self.port = port
            self.host = host

    config = MockConfig(
        name="test_connection",
        user="testuser",
        id_file=None,
        mode="direct",
        port=sshd_fixture["port"],
        host=sshd_fixture["host"],
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
    assert "Hello, World!" in metadata["history"]