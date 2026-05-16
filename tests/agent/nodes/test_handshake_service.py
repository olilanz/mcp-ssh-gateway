"""
Unit tests for NodeHandshakeService.

No live SSH or sshd fixture needed — all tests are pure unit tests.
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agent.connection_result import CommandResult
from agent.nodes.handshake import NodeHandshakeService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent  # /workspaces/mcp-ssh-gateway
HANDSHAKE_SCRIPT = PROJECT_ROOT / "resources" / "node" / "handshake.sh"

CANNED_STDOUT = (
    "hostname=testhost\n"
    "kernel_name=Linux\n"
    "kernel_release=6.1.0\n"
    "architecture=x86_64\n"
    "current_user=ubuntu\n"
    "shell=/bin/bash\n"
    "os_pretty_name=Ubuntu 22.04.3 LTS\n"
    "collected_at=2026-01-01T00:00:00Z\n"
)

CANNED_KEYS = [
    "hostname",
    "kernel_name",
    "kernel_release",
    "architecture",
    "current_user",
    "shell",
    "os_pretty_name",
    "collected_at",
]


def _make_mock_connection(stdout: str) -> MagicMock:
    """Return a mock connection whose execute() returns a CommandResult with given stdout."""
    now = datetime.utcnow()
    result = CommandResult(
        command="sh -s <<'EOF'\n...\nEOF",
        exit_code=0,
        stdout=stdout,
        stderr="",
        started_at=now,
        ended_at=now,
    )
    conn = MagicMock()
    conn.execute.return_value = result
    return conn


# ---------------------------------------------------------------------------
# Phase 1: Script file checks
# ---------------------------------------------------------------------------


def test_script_file_exists():
    """resources/node/handshake.sh must exist relative to project root."""
    assert HANDSHAKE_SCRIPT.exists(), f"Expected {HANDSHAKE_SCRIPT} to exist"


def test_script_starts_with_sh_shebang():
    """First line of handshake.sh must be '#!/bin/sh'."""
    first_line = HANDSHAKE_SCRIPT.read_text().splitlines()[0]
    assert first_line == "#!/bin/sh", f"Expected '#!/bin/sh', got {first_line!r}"


def test_script_is_readable():
    """handshake.sh must have non-zero content."""
    content = HANDSHAKE_SCRIPT.read_text()
    assert len(content) > 0, "handshake.sh is empty"


# ---------------------------------------------------------------------------
# Phase 2: _parse_output unit tests
# ---------------------------------------------------------------------------


def test_parse_well_formed_output():
    """All expected keys from CANNED_STDOUT round-trip through _parse_output."""
    svc = NodeHandshakeService()
    facts = svc._parse_output(CANNED_STDOUT)

    for key in CANNED_KEYS:
        assert key in facts, f"Expected key {key!r} in parsed facts"

    assert facts["hostname"]["value"] == "testhost"
    assert facts["kernel_name"]["value"] == "Linux"
    assert facts["architecture"]["value"] == "x86_64"
    assert facts["os_pretty_name"]["value"] == "Ubuntu 22.04.3 LTS"
    assert facts["collected_at"]["value"] == "2026-01-01T00:00:00Z"


def test_parse_value_with_equals_signs():
    """Values containing '=' characters must be preserved intact (split on first '=' only)."""
    svc = NodeHandshakeService()
    stdout = "some_key=a=b=c\ncollected_at=2026-01-01T00:00:00Z\n"
    facts = svc._parse_output(stdout)

    assert "some_key" in facts
    assert facts["some_key"]["value"] == "a=b=c"


def test_parse_partial_output():
    """Missing keys produce no entries; no exception is raised."""
    svc = NodeHandshakeService()
    stdout = "hostname=partialhost\ncollected_at=2026-01-01T00:00:00Z\n"
    facts = svc._parse_output(stdout)

    assert "hostname" in facts
    assert "kernel_name" not in facts
    assert "architecture" not in facts


def test_parse_empty_output():
    """Empty stdout returns {} without raising."""
    svc = NodeHandshakeService()
    facts = svc._parse_output("")
    assert facts == {}


# ---------------------------------------------------------------------------
# Phase 2: run() integration-style unit tests (mock connection)
# ---------------------------------------------------------------------------


def test_run_returns_facts_dict_shape():
    """With a mock connection returning canned stdout, every fact has value/source/collected_at."""
    svc = NodeHandshakeService()
    conn = _make_mock_connection(CANNED_STDOUT)
    facts = svc.run(conn)

    assert isinstance(facts, dict)
    assert len(facts) > 0

    for key, entry in facts.items():
        assert "value" in entry, f"Fact {key!r} missing 'value'"
        assert "source" in entry, f"Fact {key!r} missing 'source'"
        assert "collected_at" in entry, f"Fact {key!r} missing 'collected_at'"
        assert entry["source"] == "handshake", f"Fact {key!r} source should be 'handshake'"

    # collected_at for all facts should equal the script's own collected_at value
    expected_ts = "2026-01-01T00:00:00Z"
    for key, entry in facts.items():
        assert entry["collected_at"] == expected_ts, (
            f"Fact {key!r} collected_at should be {expected_ts!r}, got {entry['collected_at']!r}"
        )


def test_resource_root_injection(tmp_path):
    """NodeHandshakeService(resource_root=tmp_path) loads the script from the injected root."""
    # Create a minimal handshake.sh in the temp tree
    script_dir = tmp_path / "resources" / "node"
    script_dir.mkdir(parents=True)
    (script_dir / "handshake.sh").write_text(
        "#!/bin/sh\nprintf 'injected_key=injected_value\\n'\nprintf 'collected_at=2026-06-01T00:00:00Z\\n'\n"
    )

    svc = NodeHandshakeService(resource_root=tmp_path)
    conn = _make_mock_connection("injected_key=injected_value\ncollected_at=2026-06-01T00:00:00Z\n")
    facts = svc.run(conn)

    assert "injected_key" in facts
    assert facts["injected_key"]["value"] == "injected_value"
    assert facts["injected_key"]["source"] == "handshake"


def test_missing_script_returns_empty_dict(tmp_path):
    """If the handshake script does not exist, run() returns {} without raising."""
    # tmp_path has no resources/node/handshake.sh
    svc = NodeHandshakeService(resource_root=tmp_path)
    conn = _make_mock_connection("")  # should never be called
    facts = svc.run(conn)

    assert facts == {}
    conn.execute.assert_not_called()
