"""
Fixture self-verification tests.
These tests verify the spawn_sshd fixture itself works correctly.
"""
import socket
import pytest
import paramiko


@pytest.mark.functional
@pytest.mark.requires_sshd
def test_sshd_fixture_starts_and_stops(spawn_sshd):
    """Fixture yields a SpawnedSSHD and sshd accepts TCP connections."""
    assert spawn_sshd.host == "127.0.0.1"
    assert spawn_sshd.port > 1024
    # Verify port is accepting connections
    with socket.create_connection((spawn_sshd.host, spawn_sshd.port), timeout=2):
        pass


@pytest.mark.functional
@pytest.mark.requires_sshd
def test_sshd_fixture_listens_on_localhost(spawn_sshd):
    """sshd port is open on 127.0.0.1."""
    with socket.create_connection(("127.0.0.1", spawn_sshd.port), timeout=2):
        pass


@pytest.mark.functional
@pytest.mark.requires_sshd
def test_paramiko_connects_with_generated_key(spawn_sshd):
    """Raw paramiko.SSHClient.connect() succeeds with the generated client key."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=spawn_sshd.host,
        port=spawn_sshd.port,
        username=spawn_sshd.user,
        key_filename=spawn_sshd.client_key_path,
        timeout=5,
        look_for_keys=False,
        allow_agent=False,
    )
    client.close()


@pytest.mark.functional
@pytest.mark.requires_sshd
def test_paramiko_rejects_wrong_key(spawn_sshd, tmp_path):
    """paramiko.SSHClient.connect() raises AuthenticationException with a different key."""
    import subprocess
    wrong_key = str(tmp_path / "wrong_key")
    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-N", "", "-f", wrong_key],
        check=True, capture_output=True
    )
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    with pytest.raises(paramiko.AuthenticationException):
        client.connect(
            hostname=spawn_sshd.host,
            port=spawn_sshd.port,
            username=spawn_sshd.user,
            key_filename=wrong_key,
            timeout=5,
            look_for_keys=False,
            allow_agent=False,
        )
    client.close()
