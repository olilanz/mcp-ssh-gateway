# Realistic sshd Fixture Test Slice

## Purpose

Establish the gateway agent's own SSH identity, expose it as an MCP tool, and prove the full connection stack against a real local sshd process running inside the devcontainer.

This slice delivers in six phases, each building on the previous:

| Phase | Deliverable |
|-------|-------------|
| 1 | Agent SSH identity service — generate and persist the agent's own ed25519 keypair |
| 2 | `get_agent_public_key` MCP tool — expose public key, fingerprint, key type |
| 3 | Isolated local sshd fixture — correct, isolated, probe-based |
| 4 | Functional `Connection` tests against the fixture |
| 5 | Functional `ConnectionPool` tests against the fixture |
| 6 | Functional `NodeService` tests against the fixture |

Phases 4–6 depend on Phase 3. Phases 2 and 3 can be developed in parallel once Phase 1 is complete.

---

## Constraints

- No Docker-in-Docker.
- No dependency on `/data/keys`, `/etc/ssh/sshd_config`, or any permanent key material (except the agent's own persisted identity in Phase 1).
- No passwords.
- No external network targets.
- No assumptions about production sshd state.
- sshd must listen on `127.0.0.1` only, on a random high port.
- All temporary fixture files cleaned up after each test run.
- Agent identity keypair is persistent (not temporary) — it lives in a configured directory.

---

## Phase 1 — Agent SSH Identity Service

### Purpose

The gateway agent needs a stable ed25519 keypair of its own. This identity is used to authenticate outbound SSH connections to managed nodes. The public key of this identity is what an operator would install on a node to grant the agent access — the manual equivalent of running `ssh-copy-id`.

### New production files

#### `agent/identity/__init__.py`

Empty package marker.

#### `agent/identity/models.py`

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class AgentIdentity:
    key_type: str           # always "ed25519"
    public_key: str         # full OpenSSH public key string (e.g. "ssh-ed25519 AAAA...")
    fingerprint: str        # SHA256 fingerprint (e.g. "SHA256:abc123...")
    private_key_path: str   # absolute path to private key file on disk
    public_key_path: str    # absolute path to public key file on disk
```

`AgentIdentity` is a frozen dataclass — immutable after construction.

#### `agent/identity/service.py`

```python
class AgentIdentityService:
    def __init__(self, key_dir: str):
        """key_dir is the directory where agent_id_ed25519 and agent_id_ed25519.pub are stored."""

    def ensure_agent_identity(self) -> AgentIdentity:
        """Load existing keypair if present; generate and persist a new one if not.
        Returns AgentIdentity. Private key permissions set to 0o600."""

    def get_identity(self) -> AgentIdentity:
        """Return the current AgentIdentity. Raises if ensure_agent_identity() has not been called."""
```

Key file names: `agent_id_ed25519` (private), `agent_id_ed25519.pub` (public).

Key generation uses `subprocess` to call `ssh-keygen -t ed25519 -N "" -f <private_key_path>`, which is present in the devcontainer.

Fingerprint is extracted by calling `ssh-keygen -l -E sha256 -f <public_key_path>` and parsing the output.

### `run_agent.py` wiring

`AgentIdentityService` is constructed early in `run_agent()`, before the connection pool, using the configured `key_dir`. `ensure_agent_identity()` is called once at startup. The resulting `AgentIdentity` is passed to `register_tools()`.

### Phase 1 tests — `tests/agent/identity/test_agent_identity_service.py`

| Test | Validates |
|------|-----------|
| `test_ensure_creates_keypair_if_missing` | When no keys exist, `ensure_agent_identity()` creates both files |
| `test_ensure_returns_ed25519_key_type` | `identity.key_type == "ed25519"` |
| `test_ensure_public_key_starts_with_ssh_ed25519` | `identity.public_key.startswith("ssh-ed25519 ")` |
| `test_ensure_fingerprint_starts_with_sha256` | `identity.fingerprint.startswith("SHA256:")` |
| `test_ensure_reuses_existing_keypair` | Calling `ensure_agent_identity()` twice returns the same `public_key` |
| `test_private_key_permissions_are_0600` | `stat(private_key_path).st_mode & 0o777 == 0o600` |
| `test_private_key_not_returned_in_identity_fields` | `AgentIdentity` has no `private_key` string field — only a path |
| `test_get_identity_raises_if_not_ensured` | `get_identity()` before `ensure_agent_identity()` raises `RuntimeError` |

---

## Phase 2 — `get_agent_public_key` MCP Tool

### Purpose

Expose the agent's public key through the MCP API so that an operator can retrieve it and install it on a node (manually or via automation). This is the read path — the tool never returns a private key.

The manual equivalent of this tool output is what an operator would paste into `~/.ssh/authorized_keys` on a node, or pass to `ssh-copy-id`.

### Tool specification

**Tool name:** `get_agent_public_key`

**Returns:**
```json
{
  "public_key": "ssh-ed25519 AAAA... agent@gateway",
  "fingerprint": "SHA256:abc123...",
  "key_type": "ed25519"
}
```

**Never returns:** the private key string, the private key path, or any other secret material.

### `mcp_handlers.py` changes

`register_tools(mcp, node_service, agent_identity)` — add `agent_identity: AgentIdentity` parameter.

```python
@mcp.tool()
def get_agent_public_key() -> dict:
    """Return the agent's SSH public key for installation on managed nodes."""
    return {
        "public_key": agent_identity.public_key,
        "fingerprint": agent_identity.fingerprint,
        "key_type": agent_identity.key_type,
    }
```

### Phase 2 tests — `tests/agent/test_mcp_identity_tools.py`

| Test | Validates |
|------|-----------|
| `test_get_agent_public_key_tool_is_registered` | `get_agent_public_key` appears in registered tool names |
| `test_get_agent_public_key_returns_public_key` | Result contains `public_key` field |
| `test_get_agent_public_key_returns_fingerprint` | Result contains `fingerprint` field |
| `test_get_agent_public_key_returns_key_type` | Result contains `key_type` field |
| `test_get_agent_public_key_does_not_return_private_key` | Result does not contain any key named `private_key` |
| `test_get_agent_public_key_key_type_is_ed25519` | `result["key_type"] == "ed25519"` |

---

## Phase 3 — Isolated Local sshd Fixture

### Purpose

Fix the broken sshd fixture and provide a clean, probe-based, fully isolated local sshd for functional testing.

### Current state — what is broken and why

#### `tests/sshd_fixture.py` — `spawn_sshd` fixture

**Problems:**
- Uses `user="testuser"` — this user does not exist in the devcontainer. Paramiko auth fails because sshd runs under the actual current user (`vscode`).
- No `AuthorizedKeysFile` config entry — sshd falls back to system default which does not include the generated key.
- Uses `sshd` (bare command, not full path) — not reliable in all environments.
- Uses `time.sleep(0.5)` — not reliable; probe-based startup is needed.

#### `tests/agent/connectionpool/conftest.py` — `sshd_fixture`

**Problems:**
- `scope="module"` — over-aggressive scope; fixture reuse across tests causes interference.
- Does not generate an agent identity keypair — yields fake path `/tmp/test-agent-id-file`.
- Requires `mkdir /run/sshd` as root — fails in non-root devcontainer.
- Reads `sshd.pid` from file — fragile; sshd with `-D` (foreground) does not write a PID file.
- Yields `user="test-user"` — doesn't match actual system user.

**Result:** All three tests in `tests/agent/connectionpool/test_connection.py` fail at setup with errors from the broken fixture. The tests themselves are correctly written.

### Devcontainer

The [`.devcontainer/Dockerfile`](.devcontainer/Dockerfile) already installs `openssh-server` and `openssh-client`. No changes required.

### Corrected fixture design

#### Isolation requirements

```
- dedicated test-only sshd process
- generated temporary sshd_config
- generated temporary host key (ed25519)
- generated temporary client key (ed25519)
- temporary authorized_keys file
- listens only on 127.0.0.1
- binds to a random high port
- uses its own log file
- never reads /etc/ssh/sshd_config
- never relies on production sshd state
- never uses /data/keys or permanent keys
- never requires passwords
- stops the process after fixture teardown
- cleans up all temporary files
```

#### sshd config template

```
Port <random>
ListenAddress 127.0.0.1
HostKey <tempdir>/ssh_host_ed25519_key
AuthorizedKeysFile <tempdir>/authorized_keys
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
StrictModes no
PidFile none
LogLevel VERBOSE
UsePAM no
ChallengeResponseAuthentication no
```

**`StrictModes no`** — required because the temp directory parent may have permissions sshd would reject in strict mode.  
**`PidFile none`** — avoids fragile PID file read pattern.  
**`AuthorizedKeysFile <absolute path>`** — explicit absolute path so sshd finds the test key regardless of user home.

#### User determination

```python
import pwd
current_user = pwd.getpwuid(os.getuid()).pw_name
```

The test connects as the current user — the same user running sshd.

#### Startup readiness

Use TCP port probing instead of `time.sleep()`:

```python
def _wait_for_port(host, port, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(f"sshd did not listen on {host}:{port} within {timeout}s")
```

#### `SpawnedSSHD` data class

```python
@dataclass
class SpawnedSSHD:
    host: str           # always "127.0.0.1"
    port: int           # random high port
    user: str           # current Unix user (pwd.getpwuid)
    client_key_path: str  # path to generated client private key in authorized_keys
    process: subprocess.Popen
    tempdir: str
```

Note: the client key generated for the fixture is separate from the agent's persistent identity keypair. The fixture generates a throwaway keypair per test.

### Phase 3 file changes

#### Replace `tests/sshd_fixture.py`

Complete rewrite with the corrected fixture. The `spawn_sshd` fixture is `scope="function"` (one sshd per test, clean isolation).

#### Replace `tests/agent/connectionpool/conftest.py`

Remove the old broken `sshd_fixture`. Replace with a minimal comment stub:

```python
# tests/agent/connectionpool/conftest.py
#
# Functional SSH fixtures are provided via tests/sshd_fixture.py, which is
# exported by the root tests/conftest.py as spawn_sshd.
# No local fixture overrides are needed here.
```

#### Update `tests/conftest.py`

Import and re-export `spawn_sshd` from `tests/sshd_fixture`:

```python
# tests/conftest.py
from tests.sshd_fixture import spawn_sshd  # noqa: F401 — pytest discovers by name
```

Remove the current broken re-export chain through `tests/agent/connectionpool/conftest.py`.

#### Update `tests/agent/connectionpool/test_connection.py`

Add pytest markers to the three functional tests. No logic changes:

```python
@pytest.mark.functional
@pytest.mark.requires_sshd
def test_direct_connection_success(spawn_sshd): ...

@pytest.mark.functional
@pytest.mark.requires_sshd
def test_direct_connection_key_mismatch(spawn_sshd, tmp_path): ...
```

#### Update `pyproject.toml`

```toml
[tool.pytest.ini_options]
markers = [
    "functional: marks tests that require real system resources (sshd, network)",
    "requires_sshd: marks tests that require a running sshd fixture",
]
```

### Phase 3 tests — `tests/functional/test_sshd_fixture.py`

Fixture self-verification tests:

| Test | Validates |
|------|-----------|
| `test_sshd_fixture_starts_and_stops` | Fixture yields a `SpawnedSSHD`, sshd accepts TCP on port |
| `test_sshd_fixture_listens_on_localhost_only` | Port is open on `127.0.0.1`; no binding on other interfaces |
| `test_paramiko_connects_with_generated_key` | Raw `paramiko.SSHClient.connect()` succeeds with generated key |
| `test_paramiko_rejects_wrong_key` | `paramiko.SSHClient.connect()` raises `AuthenticationException` with a different key |

---

## Phase 4 — Functional `Connection` Tests

Depends on Phase 3 (corrected `spawn_sshd` fixture).

### New: `tests/functional/test_connection_functional.py`

| Test | Validates |
|------|-----------|
| `test_connection_open_succeeds` | `Connection.open()` completes without error |
| `test_connection_state_open_after_open` | `connection.get_state() == ConnectionState.OPEN` |
| `test_connection_execute_echo` | `connection.execute("echo hello")` returns `stdout="hello\n"`, `exit_code=0` |
| `test_connection_close` | `connection.close()` completes without error |
| `test_connection_state_closed_after_close` | `connection.get_state() == ConnectionState.CLOSED` |

---

## Phase 5 — Functional `ConnectionPool` Tests

Depends on Phase 3.

### New: `tests/functional/test_pool_functional.py`

| Test | Validates |
|------|-----------|
| `test_pool_get_connection_state_open` | `pool.get_connection_state(name) == "open"` after `pool.start()` |
| `test_pool_get_connection_state_not_in_pool` | `pool.get_connection_state("unknown") == "not_in_pool"` |
| `test_pool_disable_connection_closes_and_prevents_reconnect` | After `disable_connection(name)`, state stays `"closed"` across monitor cycle |

---

## Phase 6 — Functional `NodeService` Tests

Depends on Phases 3 and 5.

### New: `tests/functional/test_node_service_functional.py`

| Test | Validates |
|------|-----------|
| `test_get_node_status_reports_pool_state_open` | `NodeService.get_node_status()` returns `pool_state="open"` for fixture-backed node |
| `test_get_node_info_returns_node_entry` | `get_node_info()` returns entry with `name`, `enabled`, `pool_state` |
| `test_disable_node_closes_connection` | `disable_node(name)` → `get_node_status()` shows `pool_state` not `"open"` |

---

## Relationship to `add_node` future work

`AgentIdentityService` (Phase 1) is the foundational dependency for future node onboarding. When `add_node` is eventually implemented, it will need the agent's public key to install on the target node. The `get_agent_public_key` MCP tool (Phase 2) is how an operator retrieves that key today — the manual equivalent is running `ssh-copy-id -i <agent_public_key> user@node`.

`add_node` will call `agent_identity_service.get_identity().public_key` to obtain the key to install. This slice does not implement `add_node` installation logic; it only establishes the identity service and its read path.

---

## New file structure

```
agent/
  identity/
    __init__.py                          ← new: package marker
    models.py                            ← new: AgentIdentity dataclass
    service.py                           ← new: AgentIdentityService

tests/
  conftest.py                            ← updated: exports spawn_sshd
  sshd_fixture.py                        ← replaced: corrected, isolated fixture
  agent/
    identity/
      __init__.py                        ← new
      test_agent_identity_service.py     ← new: Phase 1 unit tests
    connectionpool/
      conftest.py                        ← replaced: comment stub
      test_connection.py                 ← markers added; no logic changes
    test_mcp_identity_tools.py           ← new: Phase 2 unit tests
  functional/
    __init__.py                          ← new
    test_sshd_fixture.py                 ← new: Phase 3 fixture self-tests
    test_connection_functional.py        ← new: Phase 4
    test_pool_functional.py              ← new: Phase 5
    test_node_service_functional.py      ← new: Phase 6
```

---

## Test run commands

```bash
# Fast unit tests only (no sshd):
pytest -m "not functional"

# All functional SSH tests:
pytest -m functional

# Phase-by-phase:
pytest tests/agent/identity/ -v
pytest tests/agent/test_mcp_identity_tools.py -v
pytest tests/functional/test_sshd_fixture.py -m functional -v
pytest tests/functional/test_connection_functional.py -m functional -v
pytest tests/functional/test_pool_functional.py -m functional -v
pytest tests/functional/test_node_service_functional.py -m functional -v

# Existing connection tests (now fixed):
pytest tests/agent/connectionpool/test_connection.py -m functional -v
```

---

## Completion gate

All of the following must be true before this slice is complete:

1. `pytest -m "not functional"` — all existing unit tests pass, no regressions
2. `pytest tests/agent/identity/ -v` — Phase 1 unit tests pass
3. `pytest tests/agent/test_mcp_identity_tools.py -v` — Phase 2 unit tests pass
4. `pytest -m functional -v` — all functional tests pass
5. `tests/agent/connectionpool/test_connection.py -m functional` — previously broken connection tests pass
6. `spawn_sshd` fixture uses current Unix user, temporary keys, absolute `AuthorizedKeysFile`, no `/run/sshd` dependency
7. `pyproject.toml` markers registered
8. `AgentIdentityService` generates if missing, reuses if present, never exposes private key string
9. `get_agent_public_key` MCP tool returns `public_key`, `fingerprint`, `key_type` only
10. No permanent keys used in fixture, no hardcoded usernames, no production sshd interaction

---

## Non-goals for this slice

- Reverse tunnel lifecycle tests
- Password onboarding tests
- Actual `add_node` installation logic (node onboarding)
- Node-scoped execution tools (`run_command_on_node`)
- Full capability discovery
- MCP gateway-level functional tests (separate future slice)
- Docker-in-Docker or external VM dependencies

---

## Delivery checklist

### Phase 1 — Agent SSH Identity Service
- [ ] Create `agent/identity/__init__.py`
- [ ] Create `agent/identity/models.py` — `AgentIdentity` frozen dataclass
- [ ] Create `agent/identity/service.py` — `AgentIdentityService` with `ensure_agent_identity()` and `get_identity()`
- [ ] Wire `AgentIdentityService` into `agent/run_agent.py`
- [ ] Create `tests/agent/identity/__init__.py`
- [ ] Create `tests/agent/identity/test_agent_identity_service.py` — 8 unit tests

### Phase 2 — `get_agent_public_key` MCP Tool
- [ ] Add `agent_identity: AgentIdentity` parameter to `register_tools()` in `agent/mcp_handlers.py`
- [ ] Add `get_agent_public_key` tool to `register_tools()`
- [ ] Update `agent/run_agent.py` to pass `AgentIdentity` to `register_tools()`
- [ ] Create `tests/agent/test_mcp_identity_tools.py` — 6 unit tests

### Phase 3 — Isolated sshd Fixture
- [ ] Replace `tests/sshd_fixture.py` — corrected, isolated fixture
- [ ] Replace `tests/agent/connectionpool/conftest.py` — comment stub
- [ ] Update `tests/conftest.py` — correct `spawn_sshd` export
- [ ] Add `@pytest.mark.functional` + `@pytest.mark.requires_sshd` to `tests/agent/connectionpool/test_connection.py`
- [ ] Register markers in `pyproject.toml`
- [ ] Create `tests/functional/__init__.py`
- [ ] Create `tests/functional/test_sshd_fixture.py` — 4 fixture self-tests

### Phase 4 — Functional Connection Tests
- [ ] Create `tests/functional/test_connection_functional.py` — 5 tests

### Phase 5 — Functional ConnectionPool Tests
- [ ] Create `tests/functional/test_pool_functional.py` — 3 tests

### Phase 6 — Functional NodeService Tests
- [ ] Create `tests/functional/test_node_service_functional.py` — 3 tests

### Final gate
- [ ] Run `pytest -m "not functional"` — all unit tests pass
- [ ] Run `pytest -m functional -v` — all functional tests pass
