"""Functional tests for add_node direct bootstrap against an isolated password sshd."""
import pytest
from agent.nodes.service import NodeService
from agent.nodes.registry import NodeRegistry
from agent.connectionpool.pool import ConnectionPool
from agent.nodes.handshake import NodeHandshakeService
from agent.identity.service import AgentIdentityService


@pytest.fixture
def bootstrap_service(tmp_path, spawn_sshd_password):
    """NodeService wired with a real AgentIdentityService for bootstrap testing."""
    key_dir = str(tmp_path / "agent_keys")
    identity_service = AgentIdentityService(key_dir=key_dir)
    identity_service.ensure_agent_identity()
    registry = NodeRegistry()
    pool = ConnectionPool([])
    pool.start()
    handshake = NodeHandshakeService()
    service = NodeService(registry, pool, handshake, identity_service)
    try:
        yield service, spawn_sshd_password
    finally:
        pool.stop()


@pytest.mark.functional
@pytest.mark.requires_password_sshd
def test_add_node_bootstrap_installs_key_and_validates(bootstrap_service):
    """add_node installs agent public key and validates key-based connection."""
    service, sshd = bootstrap_service
    result = service.add_node(
        name="bootstrap-test",
        host=sshd.host,
        port=sshd.port,
        user=sshd.username,
        password=sshd.password,
        mode="direct",
    )
    assert result.get("status") == "added"
    assert result.get("validated") is True
    assert result.get("error") is None
    # Node must be in registry
    assert service._registry.exists("bootstrap-test")

    # Fix 6: Prove node is fully operational — not just registered but executable
    cmd = service.run_command_on_node("bootstrap-test", "echo ok")
    assert cmd["exit_code"] == 0
    assert cmd["stdout"].strip() == "ok"

    # Fix 7: Assert that cfg.id_file uses the agent private key path after add_node
    cfg, _ = service._registry.get("bootstrap-test")
    assert cfg.id_file == str(service._identity_service.get_identity().private_key_path)


@pytest.mark.functional
@pytest.mark.requires_password_sshd
def test_add_node_second_call_returns_already_exists(bootstrap_service):
    """Second add_node call for the same name returns node_already_exists."""
    service, sshd = bootstrap_service
    # First add
    service.add_node(name="dup-test", host=sshd.host, port=sshd.port,
                     user=sshd.username, password=sshd.password, mode="direct")
    # Second add — must fail cleanly
    result = service.add_node(name="dup-test", host=sshd.host, port=sshd.port,
                              user=sshd.username, password=sshd.password, mode="direct")
    assert result.get("error") == "node_already_exists"


@pytest.mark.functional
@pytest.mark.requires_password_sshd
def test_add_node_password_not_logged(bootstrap_service, caplog):
    """Password must not appear in any log output during bootstrap."""
    import logging
    service, sshd = bootstrap_service
    with caplog.at_level(logging.DEBUG):
        service.add_node(
            name="log-test",
            host=sshd.host,
            port=sshd.port,
            user=sshd.username,
            password=sshd.password,
            mode="direct",
        )
    for record in caplog.records:
        assert sshd.password not in record.getMessage(), \
            f"Password appeared in log: {record.getMessage()}"


@pytest.mark.functional
@pytest.mark.requires_password_sshd
def test_add_node_authorized_keys_idempotent(bootstrap_service):
    """Running add_node twice for different names does not duplicate the key line."""
    service, sshd = bootstrap_service
    # Two separate add_node calls — key line should appear exactly once per key
    service.add_node(name="idem-1", host=sshd.host, port=sshd.port,
                     user=sshd.username, password=sshd.password, mode="direct")
    # Force second attempt with a fresh node name but same host
    service.add_node(name="idem-2", host=sshd.host, port=sshd.port,
                     user=sshd.username, password=sshd.password, mode="direct")

    # Read authorized_keys and count occurrences of the public key
    import pwd
    from pathlib import Path
    auth_keys = Path(pwd.getpwnam(sshd.username).pw_dir) / ".ssh" / "authorized_keys"
    content = auth_keys.read_text()
    identity_service = service._identity_service
    pub_key = identity_service.get_identity().public_key
    # Use the base64 key material (second token) as the unique fingerprint string
    key_token = pub_key.split()[1] if len(pub_key.split()) >= 2 else pub_key.strip()
    count = content.count(key_token)
    assert count == 1, f"Expected key to appear once, found {count} times"
