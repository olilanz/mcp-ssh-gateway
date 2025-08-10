# tests/conftest.py

import pytest
from tests.agent.connectionpool.conftest import sshd_fixture as spawn_sshd

# Re-export the fixture for test modules
@pytest.fixture
def sshd_server(spawn_sshd):
    yield spawn_sshd
