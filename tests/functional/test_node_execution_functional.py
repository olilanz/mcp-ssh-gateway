"""Phase 8 — Functional tests for node execution and handshake against a live sshd fixture."""
import os
import pytest


def _wait_for_open(pool, name, timeout=5.0):
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pool.get_connection_state(name) == "open":
            return
        time.sleep(0.1)


@pytest.fixture
def node_exec_fixture(spawn_sshd):
    from agent.connectionpool.config_loader import ConnectionConfig
    from agent.connectionpool.pool import ConnectionPool
    from agent.nodes.models import NodeConfig
    from agent.nodes.registry import NodeRegistry
    from agent.nodes.service import NodeService
    from agent.nodes.handshake import NodeHandshakeService

    conn_config = ConnectionConfig(
        name="test-node",
        user=spawn_sshd.user,
        id_file=spawn_sshd.client_key_path,
        mode="direct",
        port=spawn_sshd.port,
        host=spawn_sshd.host,
    )
    node_config = NodeConfig(
        name="test-node",
        mode="direct",
        enabled=True,
        host=spawn_sshd.host,
        port=spawn_sshd.port,
        user=spawn_sshd.user,
        id_file=spawn_sshd.client_key_path,
    )
    pool = ConnectionPool([conn_config], reconnection_delay=30)
    pool.start()
    registry = NodeRegistry()
    registry.add(node_config)
    handshake_service = NodeHandshakeService()
    service = NodeService(registry, pool, handshake_service=handshake_service)
    name = conn_config.name
    try:
        yield service, pool, name
    finally:
        pool.stop()


@pytest.mark.functional
@pytest.mark.requires_sshd
def test_run_command_on_node_echo_hello(node_exec_fixture):
    service, pool, name = node_exec_fixture
    _wait_for_open(pool, name)
    result = service.run_command_on_node(name, "echo hello")
    assert result["exit_code"] == 0
    assert result["stdout"].strip() == "hello"


@pytest.mark.functional
@pytest.mark.requires_sshd
def test_run_command_on_node_nonzero_exit_code(node_exec_fixture):
    service, pool, name = node_exec_fixture
    _wait_for_open(pool, name)
    result = service.run_command_on_node(name, "sh -c 'exit 42'")
    assert result["exit_code"] == 42


@pytest.mark.functional
@pytest.mark.requires_sshd
def test_run_command_on_node_disabled_node_rejected(node_exec_fixture):
    service, pool, name = node_exec_fixture
    _wait_for_open(pool, name)
    service.disable_node(name)
    result = service.run_command_on_node(name, "echo hello")
    assert result.get("error") == "node_disabled"
    assert result.get("name") == name


@pytest.mark.functional
@pytest.mark.requires_sshd
def test_run_command_on_node_timeout(node_exec_fixture):
    service, pool, name = node_exec_fixture
    _wait_for_open(pool, name)
    result = service.run_command_on_node(name, "sleep 10", timeout=1)
    assert result.get("error") == "timeout"
    assert result.get("name") == name


@pytest.mark.functional
@pytest.mark.requires_sshd
def test_upload_file_to_node_writes_file(node_exec_fixture):
    import base64
    service, pool, name = node_exec_fixture
    _wait_for_open(pool, name)

    content = b"hello from upload"
    data_b64 = base64.b64encode(content).decode()
    remote_path = f"/tmp/mcp_test_upload_{os.getpid()}.txt"

    result = service.upload_file_to_node(name, remote_path, data_b64, mode="0644")
    assert result.get("status") == "written"
    assert result.get("path") == remote_path

    # Verify file content via SSH command
    verify = service.run_command_on_node(name, f"cat {remote_path}")
    assert verify["exit_code"] == 0
    assert verify["stdout"].strip() == "hello from upload"

    # Cleanup
    service.run_command_on_node(name, f"rm -f {remote_path}")


@pytest.mark.functional
@pytest.mark.requires_sshd
def test_download_file_from_node_reads_file(node_exec_fixture):
    import base64
    service, pool, name = node_exec_fixture
    _wait_for_open(pool, name)

    remote_path = f"/tmp/mcp_test_download_{os.getpid()}.txt"
    expected_content = "hello from download"

    # Write file via SSH command
    write_result = service.run_command_on_node(
        name, f"printf '%s' '{expected_content}' > {remote_path}"
    )
    assert write_result["exit_code"] == 0

    # Download and verify
    result = service.download_file_from_node(name, remote_path)
    assert result.get("status") == "ok"
    assert result.get("path") == remote_path
    decoded = base64.b64decode(result["data_b64"]).decode()
    assert decoded == expected_content

    # Cleanup
    service.run_command_on_node(name, f"rm -f {remote_path}")


@pytest.mark.functional
@pytest.mark.requires_sshd
def test_handshake_populates_get_node_info(node_exec_fixture):
    service, pool, name = node_exec_fixture
    _wait_for_open(pool, name)

    # Trigger ensure_node_ready which runs the handshake
    service.run_command_on_node(name, "echo handshake-trigger")

    # Now get_node_info should show cached facts
    info_result = service.get_node_info(name=name)
    assert "nodes" in info_result
    node_info = info_result["nodes"][0]
    facts = node_info.get("info", {})

    # Verify essential facts are present
    assert "hostname" in facts
    assert facts["hostname"]["value"] != ""
    assert "architecture" in facts
    assert "current_user" in facts


@pytest.mark.functional
@pytest.mark.requires_sshd
def test_handshake_sh_runs_on_sshd_fixture(node_exec_fixture):
    """handshake.sh executes successfully on the sshd fixture and produces key=value output."""
    from agent.nodes.handshake import NodeHandshakeService
    from pathlib import Path
    service, pool, name = node_exec_fixture
    _wait_for_open(pool, name)

    # Get the open connection directly to test the script execution
    conn = pool.get_connection(name)
    assert conn is not None

    # Execute the handshake script
    handshake_svc = NodeHandshakeService()
    facts = handshake_svc.run(conn, timeout=10)

    # Verify we got a non-empty facts dict with expected keys
    assert isinstance(facts, dict)
    assert len(facts) > 0
    assert "hostname" in facts
    assert "architecture" in facts
    assert "current_user" in facts
    assert "kernel_name" in facts

    # Verify fact structure
    for key, fact in facts.items():
        assert "value" in fact, f"Fact {key!r} missing 'value' field"
        assert fact["source"] == "handshake", f"Fact {key!r} has wrong source"
        assert "collected_at" in fact, f"Fact {key!r} missing 'collected_at' field"
