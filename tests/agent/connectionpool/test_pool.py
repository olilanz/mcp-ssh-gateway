from agent.connectionpool.config_loader import ConnectionConfig
from agent.connectionpool.pool import ConnectionPool


def test_connection_pool_accepts_dict_configs(monkeypatch):
    captured = []

    class FakeConnection:
        def __init__(self, *args, **kwargs):
            captured.append({"args": args, "kwargs": kwargs})

    monkeypatch.setattr("agent.connectionpool.pool.Connection", FakeConnection)

    connection_configs = [
        {
            "name": "dict-connection",
            "user": "user",
            "id_file": "/tmp/id_rsa",
            "mode": "direct",
            "port": 22,
            "host": "127.0.0.1",
        }
    ]

    pool = ConnectionPool(connection_configs)

    assert len(pool.connections) == 1
    assert captured[0]["args"] == ()
    assert captured[0]["kwargs"]["name"] == "dict-connection"


def test_connection_pool_accepts_connection_config_objects(monkeypatch):
    captured = []

    class FakeConnection:
        def __init__(self, *args, **kwargs):
            captured.append({"args": args, "kwargs": kwargs})

    monkeypatch.setattr("agent.connectionpool.pool.Connection", FakeConnection)

    connection_configs = [
        ConnectionConfig(
            name="object-connection",
            user="user",
            id_file="/tmp/id_rsa",
            mode="direct",
            port=22,
            host="127.0.0.1",
        )
    ]

    pool = ConnectionPool(connection_configs)

    assert len(pool.connections) == 1
    assert len(captured[0]["args"]) == 1
    assert captured[0]["args"][0].name == "object-connection"
