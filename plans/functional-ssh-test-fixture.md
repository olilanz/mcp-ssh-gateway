# Realistic SSH Functional Test Fixture Slice

## Purpose

Add a reliable, self-contained local sshd fixture that proves the gateway can connect to an actual SSH server using generated passwordless keys. This fixture underpins future functional tests for `Connection`, `ConnectionPool`, `NodeService`, and MCP node APIs.

## Constraints

- No Docker-in-Docker.
- No dependency on `/data/keys` or any permanent key material.
- No passwords.
- No external network targets.
- Generated temporary keypairs only.
- sshd must listen on `127.0.0.1` only.
- Current Unix user (not a hardcoded "testuser" that doesn't exist).

---

## Existing state — what needs to change

There are currently two competing sshd fixtures with different problems:

### `tests/sshd_fixture.py` — `spawn_sshd` fixture

**Problems:**
- Uses `user="testuser"` — this user doesn't exist in the devcontainer; Paramiko auth will fail because the SSH server runs under the actual `vscode` user
- Does not write an `AuthorizedKeysFile` path the test SSH server will actually look at relative to the temporary user context
- Uses `sshd` (bare command, not full path) — may not be found in `$PATH` for `subprocess.Popen`

**Action:** Replace entirely with a corrected implementation.

### `tests/agent/connectionpool/conftest.py` — `sshd_fixture`

**Problems:**
- `scope="module"` — aggressive scope causes inter-test interference
- Does not generate an agent identity keypair — yields a fake path `/tmp/test-agent-id-file`
- Requires `mkdir /run/sshd` as root — fails in non-root devcontainer environment
- Reads `sshd.pid` from file — fragile; sshd with `-D` (foreground) may not write PID
- Yields `user="test-user"` — doesn't match actual system user

**Action:** Replace entirely. The old fixture becomes the new canonical one.

### `tests/agent/connectionpool/test_connection.py`

These tests are already written correctly against the `spawn_sshd` fixture but fail because the fixture is broken. Once the fixture is fixed, these tests should pass without modification.

### `pyproject.toml` — no pytest markers registered

Add `functional` and `requires_sshd` markers.

---

## The user problem

The core issue: sshd runs as the current Unix user (`vscode`). The `AuthorizedKeysFile` must be resolvable by sshd to a path containing the test public key. Since we can't create a system user in tests, we use an absolute path in the sshd config:

```
AuthorizedKeysFile /tmp/<tempdir>/authorized_keys
```

And sshd must be configured so `PermitUserEnvironment` is not needed. The `User` accepted by Paramiko when connecting must be the current running user (`os.getlogin()` or `pwd.getpwuid(os.getuid()).pw_name`).

---

## Corrected fixture design

### Location

Replace [`tests/sshd_fixture.py`](../tests/sshd_fixture.py) with the corrected implementation.

Remove [`tests/agent/connectionpool/conftest.py`](../tests/agent/connectionpool/conftest.py) and move its fixture registration to `tests/conftest.py` so the `spawn_sshd` fixture is available project-wide.

### Fixture behavior

```python
@pytest.fixture
def spawn_sshd():
    """
    Start a local sshd on 127.0.0.1 with a random high port.
    Uses the current system user and a generated temporary keypair.
    No passwords, no permanent keys, no external dependencies.
    """
    # 1. Create temp directory
    tempdir = tempfile.mkdtemp(prefix="mcp_sshd_test_")

    # 2. Determine current user (sshd runs as this user)
    import pwd
    current_user = pwd.getpwuid(os.getuid()).pw_name

    # 3. Generate host key
    host_key = os.path.join(tempdir, "ssh_host_rsa_key")
    subprocess.run(["ssh-keygen", "-t", "rsa", "-b", "2048", "-f", host_key, "-N", ""], check=True)

    # 4. Generate agent identity key
    agent_key = os.path.join(tempdir, "agent_id_rsa")
    subprocess.run(["ssh-keygen", "-t", "rsa", "-b", "2048", "-f", agent_key, "-N", ""], check=True)

    # 5. Write authorized_keys with generated public key
    authorized_keys = os.path.join(tempdir, "authorized_keys")
    with open(f"{agent_key}.pub") as pub:
        pubkey = pub.read()
    with open(authorized_keys, "w") as auth:
        auth.write(pubkey)
    os.chmod(authorized_keys, 0o600)

    # 6. Find free port
    port = find_free_port()

    # 7. Write sshd config — absolute paths, no /run/sshd dependency
    sshd_config = os.path.join(tempdir, "sshd_config")
    with open(sshd_config, "w") as cfg:
        cfg.write(f"""
Port {port}
ListenAddress 127.0.0.1
HostKey {host_key}
AuthorizedKeysFile {authorized_keys}
PasswordAuthentication no
PermitRootLogin no
ChallengeResponseAuthentication no
UsePAM no
StrictModes no
PidFile none
LogLevel VERBOSE
""")

    # 8. Start sshd in foreground mode
    sshd_log = os.path.join(tempdir, "sshd.log")
    with open(sshd_log, "w") as log:
        process = subprocess.Popen(
            ["/usr/sbin/sshd", "-D", "-f", sshd_config, "-e"],
            stdout=log,
            stderr=subprocess.STDOUT
        )

    # 9. Wait for sshd to be ready (probe port)
    _wait_for_port("127.0.0.1", port, timeout=5.0)

    yield SpawnedSSHD(
        host="127.0.0.1",
        port=port,
        user=current_user,
        agent_id_file=agent_key,
        process=process,
        tempdir=tempdir
    )

    # 10. Teardown
    process.terminate()
    process.wait(timeout=5)
    shutil.rmtree(tempdir, ignore_errors=True)
```

**`_wait_for_port`** probes `127.0.0.1:port` with TCP connects until it succeeds or times out — more reliable than `time.sleep(1)`.

**`StrictModes no`** is required because `authorized_keys` lives in a temp directory that sshd would otherwise reject due to permissions on the parent directory.

**`PidFile none`** avoids the fragile pid-file read pattern.

### `SpawnedSSHD` data class

```python
@dataclass
class SpawnedSSHD:
    host: str
    port: int
    user: str           # actual current Unix user — matches sshd running user
    agent_id_file: str  # path to private key that is in authorized_keys
    process: subprocess.Popen
    tempdir: str
```

---

## pytest marker registration

Add to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
    "functional: marks tests that require real system resources (sshd, network)",
    "requires_sshd: marks tests that require a running sshd fixture",
]
```

All tests using `spawn_sshd` get:
```python
@pytest.mark.functional
@pytest.mark.requires_sshd
```

Normal unit test run:
```bash
pytest                              # fast, no sshd
pytest -m functional                # functional tests only
pytest -m "not functional"          # unit tests only (same as bare pytest)
```

---

## Test scope for this slice

### Existing tests to fix

[`tests/agent/connectionpool/test_connection.py`](../tests/agent/connectionpool/test_connection.py) — already written, just needs the fixture to work. Add markers only.

### New tests

#### `tests/functional/test_sshd_fixture.py` — fixture self-test

```
test_sshd_fixture_starts_and_stops    — fixture yields, sshd accepts TCP on port
test_paramiko_connect_with_generated_key  — raw Paramiko SSHClient.connect() succeeds
```

#### `tests/functional/test_connection_functional.py` — Connection layer

```
test_connection_open_succeeds              — Connection.open() against fixture
test_connection_execute_echo              — Connection.execute("echo hello") returns "hello"
test_connection_close                      — Connection.close() succeeds cleanly
test_connection_state_after_open           — get_state() == ConnectionState.OPEN
test_connection_state_after_close          — get_state() == ConnectionState.CLOSED
```

#### `tests/functional/test_pool_functional.py` — ConnectionPool layer

```
test_pool_get_connection_state_open       — pool.get_connection_state(name) == "open" after pool.start()
test_pool_get_connection_state_closed     — pool.get_connection_state(name) == "closed" after close
test_pool_disable_prevents_reconnect      — pool.disable_connection(name) + monitor cycle → stays closed
```

#### `tests/functional/test_node_service_functional.py` — NodeService layer

```
test_get_node_status_pool_state_open      — NodeService.get_node_status() returns pool_state="open"
test_disable_node_closes_connection       — disable_node + verify pool_state="closed"
test_enable_node_allows_pool_reconnect    — enable_node clears disabled flag; pool state recoverable
```

---

## File structure after this slice

```
tests/
  conftest.py                    ← updated: exports spawn_sshd from sshd_fixture
  sshd_fixture.py                ← replaced: corrected fixture
  functional/
    __init__.py
    test_sshd_fixture.py         ← new: fixture self-tests
    test_connection_functional.py ← new: Connection layer
    test_pool_functional.py       ← new: pool layer
    test_node_service_functional.py ← new: NodeService layer
  agent/
    connectionpool/
      conftest.py                ← replaced: removed broken old fixture; defers to sshd_fixture.py
      test_connection.py         ← kept: add markers only
```

---

## Fixture consolidation

`tests/agent/connectionpool/conftest.py` is replaced with:

```python
# tests/agent/connectionpool/conftest.py
# Functional fixtures for this subpackage are provided by tests/sshd_fixture.py
# via the root tests/conftest.py. No local overrides needed.
```

`tests/conftest.py` is updated to import and re-export `spawn_sshd` from [`tests/sshd_fixture.py`](../tests/sshd_fixture.py):

```python
from tests.sshd_fixture import spawn_sshd  # noqa: F401 — re-export as fixture
```

This makes `spawn_sshd` available to all test modules.

---

## devcontainer — no changes needed

The [`.devcontainer/Dockerfile`](../.devcontainer/Dockerfile) already installs `openssh-server` and `openssh-client`. No changes required.

---

## Non-goals for this slice

- Reverse tunnel lifecycle tests
- Password onboarding tests
- Node-scoped execution tools (`run_command_on_node`)
- Full capability discovery
- MCP gateway-level functional tests (future slice)
- Docker-in-Docker or external VM dependencies

---

## Completion gate

All of the following must be true:

1. `pytest -m functional` — all functional tests pass in the devcontainer
2. `pytest -m "not functional"` — all 80 existing unit tests pass (no regressions)
3. `pytest tests/agent/connectionpool/test_connection.py -m functional` — existing connection tests pass
4. `spawn_sshd` fixture documented and `tests/conftest.py` exports it correctly
5. `pyproject.toml` markers registered
6. No permanent keys, no hardcoded users, no `/run/sshd` dependency

---

## Delivery checklist

- [ ] Replace `tests/sshd_fixture.py` with corrected fixture
- [ ] Update `tests/conftest.py` to export `spawn_sshd` (remove old broken import chain)
- [ ] Replace `tests/agent/connectionpool/conftest.py` with empty/comment stub
- [ ] Add `@pytest.mark.functional` and `@pytest.mark.requires_sshd` to `tests/agent/connectionpool/test_connection.py`
- [ ] Register markers in `pyproject.toml`
- [ ] Create `tests/functional/__init__.py`
- [ ] Create `tests/functional/test_sshd_fixture.py`
- [ ] Create `tests/functional/test_connection_functional.py`
- [ ] Create `tests/functional/test_pool_functional.py`
- [ ] Create `tests/functional/test_node_service_functional.py`
- [ ] Run `pytest -m functional -v` — all pass
- [ ] Run `pytest -m "not functional" -v` — 80 unit tests pass
