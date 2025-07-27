import pytest
from agent.connectionpool.pool import ConnectionPool

def test_connection_pool(sshd_fixture):
    connection_configs = [
        {
            "name": "test_connection_1",
            "user": "testuser",
            "id_file": None,
            "mode": "direct",
            "port": sshd_fixture["port"],
            "host": sshd_fixture["host"],
        },
        {
            "name": "test_connection_2",
            "user": "testuser",
            "id_file": None,
            "mode": "direct",
            "port": sshd_fixture["port"],
            "host": sshd_fixture["host"],
        },
    ]

    pool = ConnectionPool(connection_configs, reconnection_delay=1, reconnection_attempts=3)

    pool.start_all()
    pool_state = pool.query_pool()
    assert len(pool_state) == 2
    assert all(conn["is_running"] for conn in pool_state)

    pool.stop_all()
    pool_state = pool.query_pool()
    assert all(not conn["is_running"] for conn in pool_state)