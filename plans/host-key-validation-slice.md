# Host-Key Validation Slice

## Context

This slice replaces permissive `AutoAddPolicy` host-key trust on pooled `DirectConnection` instances with explicit `known_hosts`-based validation. It also migrates the persistent SSH state root from `/data/keys` to `/data/ssh` and establishes the `known_hosts` trust model used by both `add_node` bootstrap and normal pooled connections.

`TunnelConnection` retains `AutoAddPolicy` — reverse tunnel host-key hardening is deferred and documented explicitly as a known gap.

---

## Design Principles

- **Normal SSH known_hosts semantics, not a custom database.**  
  The gateway uses plain OpenSSH-compatible `known_hosts` format. No proprietary trust store. No hashed entries — entries are written as plain `hostname keytype base64key` (or `[host]:port keytype base64key` for non-22 ports).

- **DirectConnection is strict by default.**  
  All pooled `DirectConnection` instances use `RejectPolicy`. `AutoAddPolicy` is not a fallback for production connections. Only the password bootstrap client (operator-initiated, ephemeral) is permitted to use `AutoAddPolicy`.

- **Host-key trust is endpoint-scoped, not node-scoped.**  
  Keys identify SSH server endpoints (`host:port`), not node names or users. If two nodes share the same `host:port`, they share host-key trust. Document this caveat explicitly.

- **Mismatch is surfaced, not silently broken.**  
  When `DirectConnection.open()` catches `paramiko.BadHostKeyException`, it stores a structured `last_error` on the connection and sets state to `BROKEN`. `get_node_status` includes `last_error` so the operator sees `host_key_mismatch` rather than an opaque broken state.

- **Unknown vs mismatch are distinct errors.**  
  `unknown_host_key` — no entry at all in `known_hosts` for this endpoint.  
  `host_key_mismatch` — entry exists but the server presented a different key.  
  Both result in `BROKEN` state, but the error code differs.

- **Operator recovery is `remove_node` + `add_node`.**  
  No interactive key approval MCP tools in this slice. `remove_node` deletes the gateway-managed `known_hosts` entry when no remaining node references the same `host:port`.

- **`/data` must be a persistent volume.**  
  The gateway requires `/data/ssh/` to survive container restarts. Document this explicitly as a deployment requirement.

---

## Persistent SSH State Layout

Target layout under `/data/ssh`:

```
/data/ssh/
  agent_id_ed25519          ← agent private key (filename UNCHANGED from current)
  agent_id_ed25519.pub      ← agent public key  (filename UNCHANGED from current)
  known_hosts               ← SSH known_hosts file (new)
```

The directory is the migration (`/data/keys` → `/data/ssh`). The filenames `agent_id_ed25519` and `agent_id_ed25519.pub` are **unchanged**.

The `/data` directory must be mounted as a persistent Docker volume. Without it, the gateway loses host-key trust and the agent keypair on every container restart.

---

## Design Questions Answered

### Q1: CLI arg naming

Add `--ssh-dir` to [`app.py`](../app.py) with default `/data/ssh`.  
Keep `--agent-key-dir` as a deprecated alias that maps to the same parameter.  
The `known_hosts_path` is derived as `os.path.join(ssh_dir, "known_hosts")`.

`ConnectionPool` receives the gateway-level default `known_hosts_path` at construction. Individual `ConnectionConfig` entries may override with a per-connection `known_hosts_path` (or `allow_unknown_host_key=True` for explicit bootstrap-only bypasses), but the default is the shared gateway path.

### Q2: Migration from `/data/keys` to `/data/ssh`

`AgentIdentityService` is parameterized by `key_dir` — no change to its interface.

For existing deployments with a volume-mounted `/data/keys`:
- Use `--ssh-dir /data/keys` (note: `known_hosts` would then live at `/data/keys/known_hosts`), or
- Manually copy `/data/keys/agent_id_ed25519*` to `/data/ssh/` before upgrading.

No automatic migration code is implemented. Document both paths in `docs/DEVELOPER.md` migration note.

### Q3: How `add_node` writes `known_hosts`

During the password bootstrap connection, after `pw_client.connect()` succeeds:

```python
transport = pw_client.get_transport()
server_key = transport.get_remote_server_key()

# Plain OpenSSH-style entry — no hashing
entry = host if port == 22 else f"[{host}]:{port}"

host_keys = paramiko.HostKeys(known_hosts_path)  # loads existing
existing = host_keys.lookup(entry)

if existing and server_key.get_name() in existing:
    stored_key = existing[server_key.get_name()]
    if stored_key.asbytes() != server_key.asbytes():
        return {"error": "host_key_mismatch", "name": name, "step": "bootstrap"}
    # else: already correct, skip write
else:
    host_keys.add(entry, server_key.get_name(), server_key)
    host_keys.save(known_hosts_path)
```

If the entry is already present and **differs**, `add_node` returns `host_key_mismatch` immediately — no overwrite. The operator must use `remove_node` to delete the stale entry, then `add_node` again.

The key is written **before** closing the password connection and **before** opening the key-based validation connection.

### Q4: `ConnectionConfig` and `ConnectionPool` receive `known_hosts_path`

```python
@dataclass
class ConnectionConfig:
    name: str
    user: str
    id_file: Optional[str]
    mode: str
    port: int
    host: Optional[str]
    known_hosts_path: Optional[str] = None       # per-connection override; None = use pool default
    allow_unknown_host_key: bool = False          # explicit bypass for test/bootstrap-only contexts
```

`ConnectionPool.__init__` accepts `default_known_hosts_path: Optional[str] = None`.

`DirectConnection.open()` resolution order:
1. `config.known_hosts_path` if set → use that path
2. `pool.default_known_hosts_path` if set → use that path
3. `config.allow_unknown_host_key is True` → `AutoAddPolicy` (explicit bypass only)
4. Otherwise → `RejectPolicy` with no known_hosts → every connection will fail as `unknown_host_key`

```python
def open(self):
    with self._lock:
        self._ssh = SSHClient()
        khp = self.config.known_hosts_path or self._pool_known_hosts_path
        if khp:
            self._ssh.set_missing_host_key_policy(RejectPolicy())
            self._ssh.load_host_keys(khp)
        elif self.config.allow_unknown_host_key:
            self._ssh.set_missing_host_key_policy(AutoAddPolicy())
        else:
            self._ssh.set_missing_host_key_policy(RejectPolicy())
        try:
            self._ssh.connect(...)
        except paramiko.BadHostKeyException as exc:
            self._last_error = {
                "error": "host_key_mismatch",
                "hostname": exc.hostname,
                "expected": exc.expected_key.get_base64(),
                "got": exc.key.get_base64(),
            }
            self.state = ConnectionState.BROKEN
            return
        except Exception:
            self._last_error = {"error": "unknown_host_key"} if khp else {"error": "connect_failed"}
            self.state = ConnectionState.BROKEN
            return
```

`TunnelConnection` is not modified — it retains `AutoAddPolicy` and `_last_error` is not applicable.

### Q5: `last_error` surfaced in `get_node_status`

`BaseConnection` gains a `_last_error: Optional[dict]` field, initialized to `None`, set on any failed `open()` call. It is cleared on successful open.

`get_node_status` includes `last_error` alongside `pool_state`:

```python
{
  "name": "mynode",
  "pool_state": "broken",
  "reachable": false,
  "last_error": {"error": "host_key_mismatch", "hostname": "192.168.1.10", ...},
  ...
}
```

`NodeService._node_entry_for_status()` reads `conn.last_error` if `conn` is not None.

### Q6: `remove_node` deletes `known_hosts` entry conditionally (Option B)

`remove_node` deletes the gateway-managed `known_hosts` entry for `host:port` only when **no remaining node in the registry** references the same `host:port`.

```python
def remove_node(self, name: str) -> dict:
    config = self._registry.get(name)
    ...
    self._pool.remove_connection(name)
    self._registry.remove(name)

    # Conditionally clean known_hosts
    still_used = any(
        n.host == config.host and n.port == config.port
        for n in self._registry.all()
    )
    if not still_used and config.known_hosts_path:
        _remove_known_hosts_entry(config.host, config.port, config.known_hosts_path)

    return {"status": "removed", "name": name}
```

`_remove_known_hosts_entry` uses `paramiko.HostKeys` to load, delete, and save. If the file does not exist or the entry is absent, it is a no-op.

### Q7: Tests inject `tmp_path`-scoped `known_hosts`

Tests use `tmp_path / "known_hosts"` as the `known_hosts_path`. The `make_node_config` and `make_service` helpers in [`tests/agent/nodes/conftest.py`](../tests/agent/nodes/conftest.py) accept `known_hosts_path=None` as default. Unit tests that need it pass it explicitly.

Functional tests use a `_write_known_hosts(host, port, host_key_path, known_hosts_path)` helper (in [`tests/sshd_fixture.py`](../tests/sshd_fixture.py)) to pre-populate `known_hosts` from the fixture sshd's host key.

### Q8: `SpawnedSSHD` exposes `host_key_path`

`SpawnedSSHD` (the regular key-auth fixture) currently generates an ed25519 host key but does not store the path on the dataclass. Add `host_key_path: str` to the dataclass so functional tests can call `_write_known_hosts`.

### Q9: Reverse tunnel scope boundary

`TunnelConnection` is **not changed** in this slice. It retains `AutoAddPolicy()`. This is a **known security gap** — document it explicitly in `docs/SECURITY.md` under a "Known Gaps" section.

When reverse tunnel lifecycle is implemented, a separate host-key hardening pass will address `TunnelConnection`.

### Q10: Remove/re-add recovery story

The canonical operator recovery flow for a legitimate host-key change:

```
1. remove_node("mynode")
   → removes registry+pool entry
   → deletes known_hosts entry for host:port (if no other node uses same endpoint)

2. add_node("mynode", host=..., password=..., ...)
   → password bootstrap captures new server key
   → writes new known_hosts entry
   → key-based validation succeeds
   → registry committed
```

Tests must cover this flow end-to-end as a functional test.

---

## Architecture Flow

### Bootstrap (`add_node`) — New Flow

```
 1. Validate input (mode guard, duplicate guard)
 2. Password connect → pw_client (AutoAddPolicy — operator-initiated, ephemeral)
 3. Capture server host key from pw_client transport
 4. Check known_hosts:
      a. Entry absent → write entry
      b. Entry present, key matches → skip write (idempotent)
      c. Entry present, key differs → return {"error": "host_key_mismatch"}, abort
 5. Read agent public key
 6. Install public key to ~/.ssh/authorized_keys via SFTP
 7. Close pw_client
 8. Add ConnectionConfig(known_hosts_path=...) to pool
 9. ensure_connection_open → DirectConnection uses RejectPolicy + known_hosts
10. If conn is None → rollback pool entry + {"error": "key_auth_failed"}
11. Commit to registry with known_hosts_path
12. Return {"status": "added", "validated": True}
```

### Pooled Connection (`DirectConnection.open()`) — New Behavior

```
known_hosts_path resolved (per-connection or pool default)
  → RejectPolicy + load_host_keys
  → BadHostKeyException → BROKEN + last_error: host_key_mismatch
  → Other SSH failure with no entry → BROKEN + last_error: unknown_host_key
  → Success → OPEN, last_error cleared

allow_unknown_host_key=True (explicit bypass only)
  → AutoAddPolicy (test/bootstrap-only contexts)

No known_hosts_path and allow_unknown_host_key=False
  → RejectPolicy, no known_hosts loaded → always fails as unknown_host_key
```

### Remove/Re-add Recovery Flow

```
remove_node(name)
  → pool.remove_connection(name)
  → registry.remove(name)
  → if no other node uses same host:port → delete known_hosts entry

add_node(name, ..., password=...) [re-add]
  → password bootstrap captures new server key
  → write new known_hosts entry
  → key-based connection validates successfully
  → registry committed
```

---

## Layer Responsibility Table

| Responsibility | Layer | Method / Location |
|---|---|---|
| `/data/ssh` as SSH state root, `--ssh-dir` CLI arg | `app.py` | new `--ssh-dir` arg, default `/data/ssh` |
| Derive `known_hosts_path` from `ssh_dir` | `run_agent.py` | `os.path.join(ssh_dir, "known_hosts")` |
| Ensure `/data/ssh` dir + `known_hosts` file exist at startup | `run_agent.py` | `os.makedirs`; `open(path, "a").close()` |
| Pass default `known_hosts_path` to `ConnectionPool` | `run_agent.py` | `ConnectionPool(default_known_hosts_path=...)` |
| Pass `known_hosts_path` to `NodeService` | `run_agent.py` | `NodeService(..., known_hosts_path=...)` |
| Capture server host key during bootstrap | `NodeService.add_node()` | `transport.get_remote_server_key()` |
| Write / check host key in `known_hosts` | `NodeService.add_node()` | `paramiko.HostKeys` load + add + save |
| Return `host_key_mismatch` on bootstrap conflict | `NodeService.add_node()` | early return before SFTP step |
| Delete `known_hosts` entry on `remove_node` conditionally | `NodeService.remove_node()` | `_remove_known_hosts_entry()` helper |
| `ConnectionConfig.known_hosts_path` + `allow_unknown_host_key` | `ConnectionConfig` dataclass | two new optional fields |
| `ConnectionPool.default_known_hosts_path` | `ConnectionPool.__init__` | new parameter |
| Strict host-key enforcement on pooled connections | `DirectConnection.open()` | `RejectPolicy` + `load_host_keys` |
| `BadHostKeyException` → `last_error` + `BROKEN` | `DirectConnection.open()` | structured `_last_error` dict |
| `unknown_host_key` vs `host_key_mismatch` distinction | `DirectConnection.open()` | exception type determines error code |
| `last_error` included in `get_node_status` | `NodeService._node_entry_for_status()` | reads `conn.last_error` |
| Test `known_hosts` injection helper | `tests/sshd_fixture.py` | `_write_known_hosts()` |
| `host_key_path` on `SpawnedSSHD` dataclass | `tests/sshd_fixture.py` | add field |
| `/data` persistent volume requirement | `docs/DEVELOPER.md`, `docs/SECURITY.md` | new sections |
| Tunnel mode permissiveness documented | `docs/SECURITY.md` | "Known Gaps" section |

---

## Files to Modify

| File | Change |
|---|---|
| [`app.py`](../app.py) | Add `--ssh-dir` arg (default `/data/ssh`); deprecate `--agent-key-dir` alias |
| [`agent/run_agent.py`](../agent/run_agent.py) | Accept `ssh_dir`; ensure dir + `known_hosts` exist; pass `known_hosts_path` to `ConnectionPool` and `NodeService` |
| [`agent/connectionpool/config_loader.py`](../agent/connectionpool/config_loader.py) | Add `known_hosts_path: Optional[str] = None` and `allow_unknown_host_key: bool = False` to `ConnectionConfig` |
| [`agent/connectionpool/pool.py`](../agent/connectionpool/pool.py) | `__init__` accepts `default_known_hosts_path`; passes it to new `DirectConnection` instances |
| [`agent/connectionpool/connection.py`](../agent/connectionpool/connection.py) | `BaseConnection` gains `_last_error`; `DirectConnection.open()` uses `RejectPolicy` + known_hosts resolution; catches `BadHostKeyException` with structured error |
| [`agent/nodes/models.py`](../agent/nodes/models.py) | Add `known_hosts_path: Optional[str] = None` to `NodeConfig` |
| [`agent/nodes/service.py`](../agent/nodes/service.py) | `__init__` accepts `known_hosts_path`; `add_node()` captures + checks + writes server key; handles mismatch; `remove_node()` conditionally deletes entry; `_node_entry_for_status()` includes `last_error` |
| [`tests/sshd_fixture.py`](../tests/sshd_fixture.py) | Add `host_key_path: str` to `SpawnedSSHD`; add `_write_known_hosts()` helper |
| [`tests/agent/nodes/conftest.py`](../tests/agent/nodes/conftest.py) | Update `make_service()` and `make_node_config()` to accept `known_hosts_path` |
| [`tests/agent/connectionpool/test_connection.py`](../tests/agent/connectionpool/test_connection.py) | Unit tests for `DirectConnection` strict policy, `last_error`, `unknown_host_key` vs `host_key_mismatch` |
| [`tests/agent/nodes/test_node_lifecycle.py`](../tests/agent/nodes/test_node_lifecycle.py) | Unit tests for `add_node` known_hosts write, mismatch abort, `remove_node` conditional deletion |
| [`tests/agent/nodes/test_node_status_info.py`](../tests/agent/nodes/test_node_status_info.py) | Unit test: `get_node_status` includes `last_error` when connection is broken |
| [`tests/functional/test_connection_functional.py`](../tests/functional/test_connection_functional.py) | Functional tests for strict `DirectConnection` (matching key, empty known_hosts, wrong key) |
| [`tests/functional/test_add_node_functional.py`](../tests/functional/test_add_node_functional.py) | Functional tests: `add_node` writes key; mismatch abort; remove + re-add recovery |
| [`docs/SECURITY.md`](../docs/SECURITY.md) | Document host-key trust model; endpoint-scope caveat; operator recovery; tunnel mode Known Gap |
| [`docs/DEVELOPER.md`](../docs/DEVELOPER.md) | `/data` persistent volume requirement; `/data/ssh` layout; migration note |
| [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) | Update connection trust model section |

---

## Test Matrix

### Unit Tests

| Test | Setup | Expected |
|---|---|---|
| `test_direct_connection_reject_policy_when_known_hosts_set` | `ConnectionConfig(known_hosts_path=path)` | `RejectPolicy` set; `load_host_keys(path)` called |
| `test_direct_connection_reject_policy_when_pool_default_set` | `pool.default_known_hosts_path=path`; config has no override | `RejectPolicy` set; pool default path used |
| `test_direct_connection_auto_add_policy_when_allow_unknown` | `allow_unknown_host_key=True`; no known_hosts_path | `AutoAddPolicy` set |
| `test_direct_connection_reject_policy_no_known_hosts_no_bypass` | no `known_hosts_path`; `allow_unknown_host_key=False` | `RejectPolicy` set; no known_hosts loaded |
| `test_direct_connection_bad_host_key_sets_last_error_mismatch` | mock SSH raises `BadHostKeyException` | `last_error = {"error": "host_key_mismatch", ...}`; state `BROKEN` |
| `test_direct_connection_unknown_host_key_sets_last_error` | mock SSH raises `SSHException` after `RejectPolicy` | `last_error = {"error": "unknown_host_key"}`; state `BROKEN` |
| `test_direct_connection_success_clears_last_error` | successful open after prior failure | `last_error` is `None`; state `OPEN` |
| `test_get_node_status_includes_last_error` | connection with `last_error` set | status dict contains `last_error` key |
| `test_add_node_writes_host_key_to_known_hosts` | mocked pw_client; no existing entry | `HostKeys.save()` called; entry written |
| `test_add_node_host_key_already_matches_skip_write` | entry already present and matching | `HostKeys.save()` not called again |
| `test_add_node_host_key_mismatch_returns_error` | entry present but different key | returns `{"error": "host_key_mismatch"}`; no SFTP step |
| `test_add_node_known_hosts_path_in_connection_config` | successful `add_node` | `ConnectionConfig` passed to pool has `known_hosts_path` |
| `test_add_node_known_hosts_path_in_node_config` | successful `add_node` | `NodeConfig` in registry has `known_hosts_path` |
| `test_remove_node_deletes_known_hosts_entry_when_exclusive` | one node uses `host:port`; `remove_node` | `known_hosts` entry deleted |
| `test_remove_node_keeps_known_hosts_entry_when_shared` | two nodes share `host:port`; `remove_node` one | `known_hosts` entry preserved |
| `test_connection_config_known_hosts_path_default_none` | `ConnectionConfig(...)` no override | `known_hosts_path is None` |
| `test_connection_config_allow_unknown_host_key_default_false` | `ConnectionConfig(...)` no override | `allow_unknown_host_key is False` |

### Functional Tests

| Test | Setup | Expected |
|---|---|---|
| `test_direct_connection_succeeds_with_matching_known_hosts` | `spawn_sshd`; `_write_known_hosts` with correct key; connect | Connection opens; state `OPEN` |
| `test_direct_connection_fails_with_empty_known_hosts` | `spawn_sshd`; empty `known_hosts`; `RejectPolicy` | Open fails; state `BROKEN`; `last_error` contains `unknown_host_key` |
| `test_direct_connection_fails_when_host_key_differs` | `spawn_sshd`; wrong key in `known_hosts` | Open fails; state `BROKEN`; `last_error` contains `host_key_mismatch` |
| `test_add_node_writes_host_key_and_validates` | `spawn_sshd_password`; `add_node` | Returns `validated: True`; `known_hosts` contains server key |
| `test_add_node_mismatch_aborts_before_sftp` | `spawn_sshd_password`; pre-seed wrong key | Returns `{"error": "host_key_mismatch"}`; `authorized_keys` unchanged |
| `test_add_node_idempotent_known_hosts` | `spawn_sshd_password`; `add_node` twice (matching key) | Second call returns `already_exists`; `known_hosts` unchanged |
| `test_remove_and_readd_node_recovery` | `add_node`; mutate server (simulate key change by re-seeding `known_hosts` with wrong key); verify failure; `remove_node`; `add_node` again | Second `add_node` succeeds; new key in `known_hosts` |

---

## `known_hosts` Entry Format

Entries are written in plain OpenSSH style. **No hashing.** Rationale: the gateway manages its own `known_hosts` file; it is not the user's personal `~/.ssh/known_hosts`. Readability for operator inspection outweighs the privacy benefit of hashing.

```
# Port 22
hostname ssh-ed25519 AAAA...

# Non-standard port
[hostname]:2222 ssh-ed25519 AAAA...
```

---

## Security Scope Boundary

| Component | Host-Key Policy | Notes |
|---|---|---|
| `DirectConnection` (pooled) | **`RejectPolicy` — strict** | Default in this slice |
| Password bootstrap client in `add_node` | `AutoAddPolicy` — permissive | Operator-initiated; ephemeral; acceptable |
| `TunnelConnection` | `AutoAddPolicy` — permissive | **Known Gap** — deferred to reverse tunnel slice |

`docs/SECURITY.md` must document the `TunnelConnection` gap explicitly under a "Known Gaps" section.

---

## Deployment Requirements

### `/data` Must Be a Persistent Volume

The gateway stores both the agent identity keypair and the host trust store under `/data/ssh/`. **This directory must survive container restarts.** In Docker deployments, mount `/data` as a named volume:

```yaml
volumes:
  - ssh_gateway_data:/data
```

Without a persistent `/data`, the gateway will:
- Regenerate a new agent keypair on every restart (requiring re-installation on all nodes)
- Lose all host-key trust (requiring `remove_node` + `add_node` for every node)

Document in `docs/DEVELOPER.md` under a "Persistent State" section and in `README.md` under "Run".

---

## Migration Note

Existing deployments using `/data/keys` must take one of:
1. Pass `--ssh-dir /data/keys` — `known_hosts` will be written to `/data/keys/known_hosts`
2. Copy `/data/keys/agent_id_ed25519*` to `/data/ssh/` before upgrading (recommended)

No automatic migration code is implemented. Document in `docs/DEVELOPER.md`.

---

## Non-Goals for This Slice

- Reverse tunnel host-key hardening (`TunnelConnection` keeps `AutoAddPolicy`)
- `sshd` tunnel intake lifecycle
- Host-key accept/reject/reset MCP tools
- Custom host-key database or hashed entries
- Production image split for `sshbootstrap`
- Automatic migration of `/data/keys` to `/data/ssh` at startup
- Persistent `last_error` across process restarts

---

## Validation Expectations

After implementation:

```bash
pytest -m "not functional and not integration" -q   # zero failures, zero warnings
pytest -m functional -q                              # zero failures, zero warnings
pytest -m requires_password_sshd -q                 # zero failures (remove/re-add story covered)
```

Specific behaviors proven by tests:
- Pooled `DirectConnection` succeeds with matching `known_hosts` entry
- Pooled `DirectConnection` fails (`BROKEN`, `unknown_host_key`) when entry absent
- Pooled `DirectConnection` fails (`BROKEN`, `host_key_mismatch`) when entry present but key differs
- `get_node_status` includes `last_error` with `host_key_mismatch` details
- `add_node` writes host key before key-based validation
- `add_node` aborts with `host_key_mismatch` when pre-existing entry conflicts; does not overwrite
- `remove_node` deletes `known_hosts` entry when no other node shares the endpoint
- `remove_node` preserves `known_hosts` entry when another node shares the endpoint
- Remove + re-add recovery works end-to-end (functional test)
- No tests use developer `~/.ssh/known_hosts` — all use `tmp_path`-scoped files
- Zero new warnings introduced

---

## Deferred Work

- `TunnelConnection` host-key hardening (future reverse tunnel lifecycle slice)
- Automatic `/data/keys` → `/data/ssh` migration at startup
- Persistent `last_error` across restarts (currently in-memory only)
- Production image split (`sshbootstrap` deferred per existing TODO in `Dockerfile`)
- OpenSSH `sshd` as a controlled process for reverse tunnel intake
