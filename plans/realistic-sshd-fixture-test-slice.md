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
- No dependency on `/etc/ssh/sshd_config` or any hardcoded path.
- No passwords.
- No external network targets.
- No assumptions about production sshd state.
- sshd must listen on `127.0.0.1` only, on a random high port.
- All temporary fixture files cleaned up after each test run.
- Agent identity keypair is persistent (not temporary) — it lives in the configured `key_dir`.
- The agent's private key is never returned as a string through MCP or any API.

---

## Phase 1 — Agent SSH Identity Service

### Purpose

The gateway agent needs a stable ed25519 keypair of its own. This is the gateway's own SSH identity. The public key of this identity is what an operator would install on a node to grant the agent access — the manual equivalent of running `ssh-copy-id`.

> **Scope note:** The gateway agent identity is the default identity intended for node onboarding and future outbound node access. Current connections may still use per-connection `id_file` until SSH config and identity handling is consolidated. This slice does not replace per-connection `id_file` handling.

### Key directory configuration

`AgentIdentityService` requires an explicit `key_dir` — there is no hidden default path lookup. The key directory is configured via a new CLI argument in [`app.py`](app.py):

```bash
python3 app.py --agent-key-dir /data/keys
```

Default value: `/data/keys`.

Tests must pass a `tmp_path` fixture directory. Do not use `/data/keys` in tests.

### New production files

#### `agent/identity/__init__.py`

Empty package marker.

#### `agent/identity/models.py`

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class AgentIdentity:
    key_type: str           # always "ed25519"
    public_key: str         # full OpenSSH public key string, e.g. "ssh-ed25519 AAAA..."
    fingerprint: str        # SHA256 fingerprint, e.g. "SHA256:abc123..."
    private_key_path: str   # absolute path to private key file — path only, not the key material
    public_key_path: str    # absolute path to public key file — path only, not the key material
```

`AgentIdentity` is a frozen dataclass. It carries filesystem paths as metadata. The private key string is never stored in or returned from this object.

> **No passphrase:** The key is generated with `-N ""` (empty passphrase). The private key is protected by filesystem permissions (`0o600`), not a passphrase. This is acceptable for a non-interactive containerized agent.

#### `agent/identity/service.py`

```python
class AgentIdentityService:
    def __init__(self, key_dir: str):
        """key_dir is the directory where agent_id_ed25519 and agent_id_ed25519.pub are stored."""

    def ensure_agent_identity(self) -> AgentIdentity:
        """Load existing keypair if present; generate and persist a new one if not.
        Returns AgentIdentity. Private key permissions set to 0o600.
        
        Keypair consistency checks:
        - Both files present and consistent: return as-is.
        - Private key present, public key missing: regenerate public key from private key
          using ssh-keygen -y.
        - Public key present, private key missing: raise RuntimeError — partial state
          cannot be recovered safely; operator must intervene.
        - Both files present but do not match (fingerprint mismatch): raise RuntimeError —
          do not silently continue with inconsistent key material.
        - Neither file present: generate fresh keypair.
        """

    def get_identity(self) -> AgentIdentity:
        """Return the current AgentIdentity.
        Raises RuntimeError if ensure_agent_identity() has not been called."""
```

Key file names: `agent_id_ed25519` (private), `agent_id_ed25519.pub` (public).

Key generation uses `subprocess` to call:
```bash
ssh-keygen -t ed25519 -N "" -f <private_key_path>
```

Public key regeneration (if only private exists):
```bash
ssh-keygen -y -f <private_key_path>
```
Write stdout to `<public_key_path>`.

**Fingerprint parsing:** Extract fingerprint by calling:
```bash
ssh-keygen -l -E sha256 -f <public_key_path>
```
Typical output: `256 SHA256:abc... comment (ED25519)`

Parse by finding the token that starts with `SHA256:` — do not rely on a fixed split index:
```python
parts = output.split()
fingerprint = next(p for p in parts if p.startswith("SHA256:"))
```

### `run_agent.py` wiring

`AgentIdentityService` is constructed early in `run_agent()`, before the connection pool, using the `key_dir` from parsed args. `ensure_agent_identity()` is called once at startup. The service instance (not the identity snapshot) is passed to `register_tools()`.

### `app.py` changes

Add `--agent-key-dir` argument to the argument parser. Pass value through to `run_agent()`. Default: `/data/keys`.

### Phase 1 tests — `tests/agent/identity/test_agent_identity_service.py`

| Test | Validates |
|------|-----------|
| `test_ensure_creates_keypair_if_missing` | When no keys exist, `ensure_agent_identity()` creates both files |
| `test_ensure_returns_ed25519_key_type` | `identity.key_type == "ed25519"` |
| `test_ensure_public_key_starts_with_ssh_ed25519` | `identity.public_key.startswith("ssh-ed25519 ")` |
| `test_ensure_fingerprint_starts_with_sha256` | `identity.fingerprint.startswith("SHA256:")` |
| `test_ensure_reuses_existing_keypair` | Calling `ensure_agent_identity()` twice returns the same `public_key` |
| `test_private_key_permissions_are_0600` | `stat(private_key_path).st_mode & 0o777 == 0o600` |
| `test_private_key_string_not_in_identity_fields` | `AgentIdentity` has no string field containing raw private key material |
| `test_get_identity_raises_if_not_ensured` | `get_identity()` before `ensure_agent_identity()` raises `RuntimeError` |
| `test_missing_public_key_is_regenerated` | If public key file is deleted, `ensure_agent_identity()` reconstructs it |
| `test_missing_private_key_raises` | If only public key exists, `ensure_agent_identity()` raises `RuntimeError` |
| `test_inconsistent_keypair_raises` | If both files exist but fingerprints do not match, raises `RuntimeError` |

---

## Phase 2 — `get_agent_public_key` MCP Tool

### Purpose

Expose the agent's public key through the MCP API so that an operator can retrieve it and install it on a node. This is the read path only — the tool never returns a private key or any filesystem path.

The output of this tool is what an operator would paste into `~/.ssh/authorized_keys` on a node, or pass to `ssh-copy-id` as a manual step.

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

**Never returns:**
- `private_key` (string)
- `private_key_path`
- `public_key_path`
- `key_dir`

### `mcp_handlers.py` changes

`register_tools(mcp, node_service, agent_identity_service)` — add `agent_identity_service: AgentIdentityService` as third parameter. The handler calls `get_identity()` at call time, not at registration time.

```python
@mcp.tool()
def get_agent_public_key() -> dict:
    """Return the agent's SSH public key for installation on managed nodes."""
    identity = agent_identity_service.get_identity()
    return {
        "public_key": identity.public_key,
        "fingerprint": identity.fingerprint,
        "key_type": identity.key_type,
    }
```

Calling `get_identity()` at handler invocation time (not at registration time) aligns with future reload or rotation semantics — even though rotation is not implemented in this slice.

### Phase 2 tests — `tests/agent/test_mcp_identity_tools.py`

| Test | Validates |
|------|-----------|
| `test_get_agent_public_key_tool_is_registered` | `get_agent_public_key` appears in registered tool names |
| `test_get_agent_public_key_returns_public_key` | Result contains `public_key` field |
| `test_get_agent_public_key_returns_fingerprint` | Result contains `fingerprint` field |
| `test_get_agent_public_key_returns_key_type` | Result contains `key_type` field |
| `test_get_agent_public_key_does_not_return_private_key` | Result does not contain any key named `private_key` |
| `test_get_agent_public_key_does_not_return_paths` | Result does not contain `private_key_path`, `public_key_path`, or `key_dir` |
| `test_get_agent_public_key_key_type_is_ed25519` | `result["key_type"] == "ed25519"` |

---

## Phase 3 — Isolated Local sshd Fixture

### Purpose

Fix the broken sshd fixture and provide a clean, probe-based, fully isolated local sshd for functional testing.

### Current state — what is broken and why

#### `tests/sshd_fixture.py` — `spawn_sshd` fixture

- Uses `user="testuser"` — this user does not exist in the devcontainer.
- No `AuthorizedKeysFile` config entry — sshd falls back to system default.
- Uses `sshd` (bare command) — not reliable in all environments.
- Uses `time.sleep(0.5)` — not reliable; probe-based startup needed.

#### `tests/agent/connectionpool/conftest.py` — `sshd_fixture`

- `scope="module"` — over-aggressive; causes inter-test interference.
- Yields fake path `/tmp/test-agent-id-file` — not a real key.
- Requires `mkdir /run/sshd` as root — fails in non-root devcontainer.
- Reads `sshd.pid` from file — fragile; sshd with `-D` does not write a PID file.
- Yields `user="test-user"` — does not match actual system user.

**Result:** All three tests in [`tests/agent/connectionpool/test_connection.py`](tests/agent/connectionpool/test_connection.py) fail at setup. The tests themselves are correctly written.

### Devcontainer

The [`.devcontainer/Dockerfile`](.devcontainer/Dockerfile) already installs `openssh-server` and `openssh-client`. No changes required.

### Corrected fixture design

#### Isolation requirements

```
- dedicated test-only sshd process
- generated temporary sshd_config
- generated temporary host key (ed25519)
- generated temporary client key (ed25519) — separate from agent persistent identity
- temporary authorized_keys file with absolute path
- listens only on 127.0.0.1
- binds to a random high port
- uses its own log file
- never reads /etc/ssh/sshd_config
- never uses /data/keys or any persistent key
- never requires passwords
- stops the process after fixture teardown
- cleans up all temporary files
```

The client keypair generated for the fixture is throwaway per test. It is separate from the agent's persistent identity keypair.

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

> **Algorithm restrictions:** Do not add `HostKeyAlgorithms` or `PubkeyAcceptedAlgorithms` restrictions unless tests fail on a specific environment without them. Avoid premature portability constraints.

#### User determination

```python
import pwd
current_user = pwd.getpwuid(os.getuid()).pw_name
```

The test connects as the current user — the same user running sshd.

#### Startup readiness

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
    host: str             # always "127.0.0.1"
    port: int             # random high port
    user: str             # current Unix user (pwd.getpwuid)
    client_key_path: str  # path to generated throwaway client private key
    process: subprocess.Popen
    tempdir: str
```

### Phase 3 file changes

#### Replace `tests/sshd_fixture.py`

Complete rewrite with the corrected fixture. `spawn_sshd` is `scope="function"`.

#### Replace `tests/agent/connectionpool/conftest.py`

```python
# tests/agent/connectionpool/conftest.py
#
# Functional SSH fixtures are provided via tests/sshd_fixture.py, which is
# exported by the root tests/conftest.py as spawn_sshd.
# No local fixture overrides are needed here.
```

#### Update `tests/conftest.py`

```python
# tests/conftest.py
from tests.sshd_fixture import spawn_sshd  # noqa: F401 — pytest discovers by name
```

#### Update `tests/agent/connectionpool/test_connection.py`

Add pytest markers. No logic changes:

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

| Test | Validates |
|------|-----------|
| `test_sshd_fixture_starts_and_stops` | Fixture yields a `SpawnedSSHD`, sshd accepts TCP on port |
| `test_sshd_fixture_listens_on_localhost_only` | Port is open on `127.0.0.1`; no binding on other interfaces |
| `test_paramiko_connects_with_generated_key` | Raw `paramiko.SSHClient.connect()` succeeds with generated key |
| `test_paramiko_rejects_wrong_key` | `paramiko.SSHClient.connect()` raises `AuthenticationException` with a different key |

---

## Phase 4 — Functional `Connection` Tests

Depends on Phase 3.

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

### Pool teardown

Every functional `ConnectionPool` test must call `pool.stop()` in teardown or a `try/finally` block. The pool monitor uses `OneShotRepeatingTimer`; leaked timers cause flaky test behaviour.

```python
@pytest.fixture
def pool_fixture(spawn_sshd):
    pool = build_pool_from_sshd(spawn_sshd)
    pool.start()
    try:
        yield pool
    finally:
        pool.stop()
```

### New: `tests/functional/test_pool_functional.py`

| Test | Validates |
|------|-----------|
| `test_pool_get_connection_state_open` | `pool.get_connection_state(name) == "open"` after `pool.start()` |
| `test_pool_get_connection_state_not_in_pool` | `pool.get_connection_state("unknown") == "not_in_pool"` |
| `test_pool_disable_connection_closes_and_prevents_reconnect` | After `disable_connection(name)`, state stays `"closed"` across monitor cycle |

---

## Phase 6 — Functional `NodeService` Tests

Depends on Phases 3 and 5.

### Pool teardown

Same teardown rule as Phase 5 — `pool.stop()` must be called in every test.

### New: `tests/functional/test_node_service_functional.py`

| Test | Validates |
|------|-----------|
| `test_get_node_status_reports_pool_state_open` | `NodeService.get_node_status()` returns `pool_state="open"` for fixture-backed node |
| `test_get_node_info_returns_node_entry` | `get_node_info()` returns entry with `name`, `enabled`, `pool_state` |
| `test_disable_node_closes_connection` | `disable_node(name)` → `get_node_status()` shows `pool_state` not `"open"` |

---

## Relationship to `add_node` future work

`AgentIdentityService` (Phase 1) is the foundational dependency for future node onboarding. When `add_node` is eventually implemented, it will need the agent's public key to install on the target node:

```python
agent_identity_service.get_identity().public_key
```

The `get_agent_public_key` MCP tool (Phase 2) is how an operator retrieves that key today. The manual operator equivalent is:

```bash
ssh-copy-id -i <agent_public_key_path> user@node
```

This slice does not implement `add_node` installation logic; it establishes the identity service and its read path only.

---

## Documentation changes

This slice introduces the gateway's own SSH identity as a product concept. Add small targeted updates to:

### `docs/ARCHITECTURE.md`

Add a new short section under the agent boundary:

```
### Agent SSH Identity
The gateway agent has its own SSH identity — a persistent ed25519 keypair stored in
the configured key directory. The public key may be retrieved via the
get_agent_public_key MCP tool. The private key is never exposed through MCP or any API.
```

### `docs/SECURITY.md`

Extend the existing "Assisted Node Onboarding" or "Passwordless Connectivity" section:

```
The gateway agent's SSH public key is available through the get_agent_public_key
MCP tool. An operator installs this key on a managed node to grant the agent access.
The private key is protected by filesystem permissions (0600) and is never returned
through any API.
```

### `docs/TESTING_STRATEGY.md`

Add a note on functional SSH tests:

```
## Functional SSH tests
Functional tests marked @pytest.mark.functional require a running local sshd process.
The spawn_sshd fixture (tests/sshd_fixture.py) starts an isolated sshd inside the
devcontainer using temporary keys, a random high port, and a generated sshd_config.
Run with: pytest -m functional
```

---

## New file structure

```
agent/
  identity/
    __init__.py                          ← new: package marker
    models.py                            ← new: AgentIdentity frozen dataclass
    service.py                           ← new: AgentIdentityService

tests/
  conftest.py                            ← updated: exports spawn_sshd
  sshd_fixture.py                        ← replaced: corrected, isolated fixture
  agent/
    identity/
      __init__.py                        ← new
      test_agent_identity_service.py     ← new: Phase 1 unit tests (11 tests)
    connectionpool/
      conftest.py                        ← replaced: comment stub
      test_connection.py                 ← markers added; no logic changes
    test_mcp_identity_tools.py           ← new: Phase 2 unit tests (7 tests)
  functional/
    __init__.py                          ← new
    test_sshd_fixture.py                 ← new: Phase 3 fixture self-tests (4 tests)
    test_connection_functional.py        ← new: Phase 4 (5 tests)
    test_pool_functional.py              ← new: Phase 5 (3 tests)
    test_node_service_functional.py      ← new: Phase 6 (3 tests)
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
2. `pytest tests/agent/identity/ -v` — Phase 1 unit tests pass (11 tests)
3. `pytest tests/agent/test_mcp_identity_tools.py -v` — Phase 2 unit tests pass (7 tests)
4. `pytest -m functional -v` — all functional tests pass
5. `tests/agent/connectionpool/test_connection.py -m functional` — previously broken connection tests pass
6. `spawn_sshd` fixture uses current Unix user, temporary keys, absolute `AuthorizedKeysFile`, no `/run/sshd` dependency
7. `pyproject.toml` markers registered
8. `AgentIdentityService` generates if missing, reuses if present, fails clearly on inconsistent keypair state
9. `get_agent_public_key` MCP tool returns `public_key`, `fingerprint`, `key_type` only — no paths, no private key
10. All functional `ConnectionPool` tests call `pool.stop()` in teardown
11. No permanent keys used in fixture, no hardcoded usernames, no production sshd interaction
12. Docs updated: `ARCHITECTURE.md`, `SECURITY.md`, `TESTING_STRATEGY.md`

---

## Non-goals for this slice

- Reverse tunnel lifecycle tests
- Password onboarding tests
- Actual `add_node` installation logic
- Key passphrase support or key rotation
- Node-scoped execution tools (`run_command_on_node`)
- Full capability discovery
- MCP gateway-level functional tests (separate future slice)
- Docker-in-Docker or external VM dependencies

---

## Delivery checklist

### Phase 1 — Agent SSH Identity Service
- [ ] Create `agent/identity/__init__.py`
- [ ] Create `agent/identity/models.py` — `AgentIdentity` frozen dataclass
- [ ] Create `agent/identity/service.py` — `AgentIdentityService` with keypair consistency checks
- [ ] Add `--agent-key-dir` argument to `app.py` (default `/data/keys`)
- [ ] Wire `AgentIdentityService` into `agent/run_agent.py` using configured `key_dir`
- [ ] Create `tests/agent/identity/__init__.py`
- [ ] Create `tests/agent/identity/test_agent_identity_service.py` — 11 unit tests

### Phase 2 — `get_agent_public_key` MCP Tool
- [ ] Update `register_tools()` signature to accept `agent_identity_service: AgentIdentityService`
- [ ] Add `get_agent_public_key` tool — calls `get_identity()` at invocation time
- [ ] Update `agent/run_agent.py` to pass `AgentIdentityService` to `register_tools()`
- [ ] Create `tests/agent/test_mcp_identity_tools.py` — 7 unit tests

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
- [ ] Create `tests/functional/test_pool_functional.py` — 3 tests with `pool.stop()` teardown

### Phase 6 — Functional NodeService Tests
- [ ] Create `tests/functional/test_node_service_functional.py` — 3 tests with `pool.stop()` teardown

### Documentation
- [ ] Update `docs/ARCHITECTURE.md` — Agent SSH Identity section
- [ ] Update `docs/SECURITY.md` — agent public key access note
- [ ] Update `docs/TESTING_STRATEGY.md` — functional SSH tests note

### Final gate
- [ ] Run `pytest -m "not functional"` — all unit tests pass
- [ ] Run `pytest -m functional -v` — all functional tests pass
