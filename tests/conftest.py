# tests/conftest.py

import pytest
from .sshd_fixture import spawn_sshd

# Re-export the fixture for test modules
@pytest.fixture
def sshd_server(spawn_sshd):
    yield spawn_sshd
