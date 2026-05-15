# Realistic sshd Fixture Test Slice

## Purpose

Add a reliable, self-contained local sshd test fixture and a suite of functional tests that prove the gateway can connect to an actual SSH server using generated passwordless keys.

This fixture underpins future functional tests for:
- `Connection` and `ConnectionPool`
- `NodeService`
- MCP node APIs with real connection state
- Eventually: node-scoped command execution

---

## Constraints

- No Docker-in-Docker.
- No dependency on `/data/keys`, `/etc/ssh/sshd_config`, or any permanent key material.
- No passwords.
- No external network targets.
- No assumptions about production sshd state.
- Generated temporary keypairs only.
- sshd must listen on `127.0.0.1` only, on a random high port.
- All temporary files cleaned up after each test run.

---

## Current state — what is broken and why

### `tests/sshd_fixture.py` — `spawn_sshd` fixture

**Problems:**
- Uses `user="testuser"` — this user does not exist in the devcontainer. Paramiko auth fails because sshd runs under the actual current user (`vscode`).
- No `AuthorizedKeysFile` config entry — sshd falls back to system default which does not include the generated key.
- Uses `sshd` (bare command, not full path) — not reliable in all environments.
- Uses `time.sleep(0.5)` — not reliable; probe-based startup is needed.

### `tests/agent/connectionpool/conftest.py` — `sshd_fixture`

**Problems:**
- `scope="module"` — over-aggressive scope; fixture reuse across tests causes interference.
- Does not generate an agent identity keypair — yields fake path `/tmp/test-agent-id-file`.
- Requires `mkdir /run/sshd` as root — fails in non-root devcontainer.
- Reads `sshd.pid` from file — fragile; sshd with `-D` (foreground) does not write a PID file.
- Yields `user="test-user"` — doesn't match actual system user.

**Result:** All three tests in `tests/agent/connectionpool/test_connection.py` fail at setup with errors from the broken fixture. The tests themselves are correctly written.

### `tests/agent/connectionpool/test_connection.py`

Tests are correctly written. They fail only because the fixture is broken. Once the fixture is fixed, these tests should pass without logic changes. Add markers only.

### `pyproject.toml`

No pytest markers registered. Add `functional` and `requires_sshd`.

---

## Devcontainer

The [`.devcontainer/Dockerfile`](.devcontainer/Dockerfile) already installs `openssh-server` and `openssh-client`. No changes required.

---

## Corrected fixture design

### Isolation requirements

The test sshd must be completely isolated from any production sshd state:

```
- dedicated test-only sshd process
- generated temporary sshd_config
- generated temporary host key (ed25519 preferred; rsa as fallback)
- generated temporary client key
- temporary authorized_keys file
- listens only on 127.0.0.1
- binds to a random high port
- uses its own log file
- never reads /etc/ssh/sshd_config
- never relies on production sshd state
- never uses /data/keys
- never uses permanent keys
- never requires passwords
- stops the process after fixture
- cleans up all temporary files
```

### sshd config template

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

### User determination

```python
import pwd
current_user = pwd.getpwuid(os.getuid()).pw_name
```

The test connects as the current user — the same user running sshd. This matches how sshd resolves `AuthorizedKeysFile`.

### Startup readiness

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

### `SpawnedSSHD` data class

```python
@dataclass
class SpawnedSSHD:
    host: str           # always "127.0.0.1"
    port: int           # random high port
    user: str           # current Unix user (pwd.getpwuid)
    agent_id_file: str  # path to private key in authorized_keys
    process: subprocess.Popen
    tempdir: str
```

---

## File changes

### Replace `tests/sshd_fixture.py`

Complete rewrite with the corrected fixture. The `spawn_sshd` fixture is `scope="function"` (one sshd per test, clean isolation).

### Replace `tests/agent/connectionpool/conftest.py`

Remove the old broken `sshd_fixture`. Replace with a minimal stub or empty file:

```python
# tests/agent/connectionpool/conftest.py
#
# Functional SSH fixtures are provided via tests/sshd_fixture.py, which is
# exported by the root tests/conftest.py as spawn_sshd.
# No local fixture overrides are needed here.
```

### Update `tests/conftest.py`

Import and re-export `spawn_sshd` from `tests/sshd_fixture`:

```python
# tests/conftest.py
from tests.sshd_fixture import spawn_sshd  # noqa: F401 — pytest discovers by name
```

Remove the current broken re-export chain through `tests/agent/connectionpool/conftest.py`.

### Update `tests/agent/connectionpool/test_connection.py`

Add pytest markers to the three functional tests. No logic changes:

```python
@pytest.mark.functional
@pytest.mark.requires_sshd
def test_direct_connection_success(spawn_sshd): ...

@pytest.mark.functional
@pytest.mark.requires_sshd
def test_direct_connection_key_mismatch(spawn_sshd, tmp_path): ...
```

The tunnel connection test (`test_tunnel_connection_success`) can remain without a marker for now — it requires more setup and can be evaluated separately.

### Update `pyproject.toml`

```toml
[tool.pytest.ini_options]
markers = [
    "functional: marks tests that require real system resources (sshd, network)",
    "requires_sshd: marks tests that require a running sshd fixture",
]
```

### New: `tests/functional/__init__.py`

Empty package marker.

### New: `tests/functional/test_sshd_fixture.py`

Fixture self-verification tests:

| Test | Validates |
|------|-----------|
| `test_sshd_fixture_starts_and_stops` | Fixture yields a `SpawnedSSHD`, sshd accepts TCP on port |
| `test_sshd_fixture_listens_on_localhost_only` | Port is open on `127.0.0.1`; no binding on other interfaces |
| `test_paramiko_connects_with_generated_key` | Raw `paramiko.SSHClient.connect()` succeeds with generated key |
| `test_paramiko_rejects_wrong_key` | `paramiko.SSHClient.connect()` raises `AuthenticationException` with a different key |

### New: `tests/functional/test_connection_functional.py`

`Connection` layer functional tests:

| Test | Validates |
|------|-----------|
| `test_connection_open_succeeds` | `Connection.open()` completes without error |
| `test_connection_state_open_after_open` | `connection.get_state() == ConnectionState.OPEN` |
| `test_connection_execute_echo` | `connection.execute("echo hello")` returns `stdout="hello\n"`, `exit_code=0` |
| `test_connection_close` | `connection.close()` completes without error |
| `test_connection_state_closed_after_close` | `connection.get_state() == ConnectionState.CLOSED` |

### New: `tests/functional/test_pool_functional.py`

`ConnectionPool` layer functional tests:

| Test | Validates |
|------|-----------|
| `test_pool_get_connection_state_open` | `pool.get_connection_state(name) == "open"` after `pool.start()` |
| `test_pool_get_connection_state_not_in_pool` | `pool.get_connection_state("unknown") == "not_in_pool"` |
| `test_pool_disable_connection_closes_and_prevents_reconnect` | After `disable_connection(name)`, state stays `"closed"` across monitor cycle |

### New: `tests/functional/test_node_service_functional.py`

`NodeService` layer functional tests:

| Test | Validates |
|------|-----------|
| `test_get_node_status_reports_pool_state_open` | `NodeService.get_node_status()` returns `pool_state="open"` for fixture-backed node |
| `test_get_node_info_returns_node_entry` | `get_node_info()` returns node entry with `name`, `enabled`, `pool_state` |
| `test_disable_node_closes_connection` | `disable_node(name)` → `get_node_status()` shows `pool_state` not `"open"` |

---

## New file structure

```
tests/
  conftest.py                          ← updated: exports spawn_sshd from sshd_fixture
  sshd_fixture.py                      ← replaced: corrected, isolated fixture
  functional/
    __init__.py                        ← new
    test_sshd_fixture.py               ← new: fixture self-tests
    test_connection_functional.py      ← new: Connection layer
    test_pool_functional.py            ← new: ConnectionPool layer
    test_node_service_functional.py    ← new: NodeService layer
  agent/
    connectionpool/
      conftest.py                      ← replaced: comment stub (broken fixture removed)
      test_connection.py               ← markers added; no logic changes
```

---

## Test run commands

```bash
# Fast unit tests only (no sshd):
pytest

# All functional SSH tests:
pytest -m functional

# Specific layers:
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

1. `pytest -m "not functional"` — all 80 existing unit tests pass (no regressions)
2. `pytest -m functional -v` — all new functional tests pass
3. `tests/agent/connectionpool/test_connection.py -m functional` — existing connection tests pass (was broken before)
4. `spawn_sshd` fixture uses current Unix user, temporary keys, absolute `AuthorizedKeysFile`, no `/run/sshd` dependency
5. `pyproject.toml` markers registered
6. No permanent keys, no hardcoded usernames, no production sshd interaction

---

## Non-goals for this slice

- Reverse tunnel lifecycle tests
- Password onboarding tests
- Node-scoped execution tools (`run_command_on_node`)
- Full capability discovery
- MCP gateway-level functional tests (separate future slice)
- Docker-in-Docker or external VM dependencies

---

## Delivery checklist

- [ ] Replace `tests/sshd_fixture.py` — corrected, isolated fixture
- [ ] Replace `tests/agent/connectionpool/conftest.py` — comment stub
- [ ] Update `tests/conftest.py` — correct `spawn_sshd` export
- [ ] Add `@pytest.mark.functional` + `@pytest.mark.requires_sshd` to `tests/agent/connectionpool/test_connection.py`
- [ ] Register markers in `pyproject.toml`
- [ ] Create `tests/functional/__init__.py`
- [ ] Create `tests/functional/test_sshd_fixture.py`
- [ ] Create `tests/functional/test_connection_functional.py`
- [ ] Create `tests/functional/test_pool_functional.py`
- [ ] Create `tests/functional/test_node_service_functional.py`
- [ ] Run `pytest -m "not functional"` — 80 unit tests pass
- [ ] Run `pytest -m functional -v` — all functional tests pass
