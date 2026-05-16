# Host-Key Validation Slice

## Context

This slice replaces permissive `AutoAddPolicy` host-key trust on pooled SSH connections with explicit `known_hosts`-based validation. It also migrates the persistent SSH state root from `/data/keys` to `/data/ssh` and establishes the `known_hosts` trust model used by both `add_node` bootstrap and normal pooled connections.

Reverse tunnel lifecycle remains deferred. `TunnelConnection` keeps `AutoAddPolicy` and is not changed in this slice.

---

## Design Principles

- **Normal SSH known_hosts semantics, not a custom database.**  
  The gateway uses OpenSSH-compatible `known_hosts` format. No proprietary trust store.

- **Host-key trust is endpoint-scoped, not node-scoped.**  
  Keys identify SSH server endpoints (host:port), not node names or users.  
  If two nodes share the same host:port, they share host-key trust. Re-adding one access path may repair trust for the others because the SSH server identity is common. Document this caveat explicitly.

- **No accept/reject/reset host-key MCP tools in this slice.**  
  Operator recovery from a legitimate host-key change is `remove_node` + `add_node`. The gateway does not provide interactive key approval.

- **`remove_node` does NOT delete `known_hosts` entries.**  
  Removing a node removes its registry/pool entry but leaves host-key trust intact. The same endpoint may be re-added without needing to re-trust the server.

---

## Persistent SSH State Layout

Target layout under `/data/ssh`:

```
/data/ssh/
  agent_ed25519          ← agent private key (was: /data/keys/agent_id_ed25519)
  agent_ed25519.pub      ← agent public key  (was: /data/keys/agent_id_ed25519.pub)
  known_hosts            ← SSH known_hosts file (new)
```

The `/data/ssh` directory is the single persistent SSH state root for the gateway process. It holds both the agent identity and the host trust store.

---

## Design Questions Answered

### Q1: `--agent-key-dir` vs `--ssh-dir`

Add `--ssh-dir` to [`app.py`](../app.py) with default `/data/ssh`.  
Keep `--agent-key-dir` as a deprecated alias that maps to `--ssh-dir` for backward compatibility.  
`AgentIdentityService` is parameterized by `key_dir` — no change to its interface.  
The known_hosts path is derived as `os.path.join(ssh_dir, "known_hosts")`.

### Q2: Migration from `/data/keys` to `/data/ssh`

`AgentIdentityService` looks for the keypair in whatever directory it is given. Changing the default from `/data/keys` to `/data/ssh` is sufficient for new deployments.

For existing deployments with a volume-mounted `/data/keys`:
- Use `--agent-key-dir /data/keys` (preserved alias) to continue using the old path, OR
- Manually copy `/data/keys/agent_id_ed25519*` to `/data/ssh/` before upgrading.
- Document both paths in a migration note.

No automatic migration code is implemented in this slice. The operator is responsible for volume state migration.

Key filename alignment: keep existing `agent_id_ed25519` / `agent_id_ed25519.pub` filenames — do not rename the files. The directory is the migration, not the filenames.

### Q3: How `add_node` writes `known_hosts`

During the password bootstrap connection, after `pw_client.connect()` succeeds:

```python
transport = pw_client.get_transport()
server_key = transport.get_remote_server_key()
# Format: "hostname keytype base64key" or "[hostname]:port keytype base64key"
key_entry = paramiko.HostKeys.hash_host(host) if port == 22 else f"[{host}]:{port}"
# Use paramiko.HostKeys to write the entry
host_keys = paramiko.HostKeys(known_hosts_path)  # loads existing
host_keys.add(key_entry, server_key.get_name(), server_key)
host_keys.save(known_hosts_path)
```

The key is written **before** closing the password connection and **before** opening the key-based validation connection.

Then the key-based `ConnectionConfig` connection uses strict known_hosts: `RejectPolicy()` + `load_host_keys(known_hosts_path)`.

### Q4: `DirectConnection` loads and enforces `known_hosts`

`DirectConnection` needs access to the `known_hosts_path`. Two options:

**Option A (preferred):** Add `known_hosts_path: Optional[str]` to `ConnectionConfig`.  
- If set: use `RejectPolicy()` + `load_host_keys(path)`.  
- If None: use `AutoAddPolicy()` (backward compat, connection-file nodes not yet migrated).

**Option B:** Pass `known_hosts_path` to `DirectConnection` as a separate constructor arg.

Option A is chosen because `ConnectionConfig` is the stable data interface between pool, service, and registry. The known_hosts path is part of the connection's trust configuration.

```python
@dataclass
class ConnectionConfig:
    name: str
    user: str
    id_file: Optional[str]
    mode: str
    port: int
    host: Optional[str]
    known_hosts_path: Optional[str] = None  # NEW — None means AutoAddPolicy (legacy)
```

`DirectConnection.open()` behavior:
```python
self._ssh = SSHClient()
if self.known_hosts_path:
    self._ssh.set_missing_host_key_policy(RejectPolicy())
    self._ssh.load_host_keys(self.known_hosts_path)
else:
    self._ssh.set_missing_host_key_policy(AutoAddPolicy())
```

Existing connections loaded from `connections.json` (no `known_hosts_path`) use `AutoAddPolicy` until they are re-registered via `add_node`. This maintains backward compatibility.

### Q5: Tests inject a temporary `known_hosts` path

Tests use `tmp_path / "known_hosts"` as the `known_hosts_path`:

```python
known_hosts = tmp_path / "known_hosts"
known_hosts.write_text("")  # empty file = no trust yet
conn_config = ConnectionConfig(..., known_hosts_path=str(known_hosts))
```

The `make_node_config` helper in [`tests/agent/nodes/conftest.py`](../tests/agent/nodes/conftest.py) gets a `known_hosts_path=None` default. Unit tests that need it pass it explicitly.

### Q6: Functional fixtures expose their host key

`SpawnedSSHD` and `SpawnedSSHDPassword` already have `host_key_path` (the path to the generated ed25519 host key for the fixture sshd).

A fixture helper writes the fixture host key into the test `known_hosts`:

```python
def _write_known_hosts(host, port, host_key_path, known_hosts_path):
    """Write a fixture sshd's host key into a known_hosts file."""
    import paramiko
    host_key = paramiko.Ed25519Key(filename=host_key_path)
    if port == 22:
        entry = host
    else:
        entry = f"[{host}]:{port}"
    hk = paramiko.HostKeys()
    hk.add(entry, "ssh-ed25519", host_key)
    hk.save(known_hosts_path)
```

`SpawnedSSHD` must expose `host_key_path` (it currently generates but does not store the host key path on the dataclass).

### Q7: Error key for host-key mismatch

When `DirectConnection.open()` fails due to host-key rejection, Paramiko raises `paramiko.SSHException` or `paramiko.BadHostKeyException`. The connection state is set to `BROKEN`.

From the pool's perspective, `ensure_connection_open()` returns `None` when open fails. The `NodeService` returns `{"error": "connection_not_open", "name": name}`.

For `add_node` key validation step, if `ensure_connection_open` returns None after bootstrap, return:
```python
{"error": "key_auth_failed", "name": name, "step": "key_validation"}
```

This is unchanged from the current contract. The specific reason (host-key mismatch vs. auth failure) is logged but not surfaced in the MCP response — the operator checks logs or re-runs `add_node`.

If we want to surface host-key specifically, we would need to catch `BadHostKeyException` in `DirectConnection.open()` and set a structured `last_error` field. That is **deferred** — not in this slice.

### Q8: Surface in `get_node_status` and `get_node_info(refresh=True)`

**`get_node_status`:** Already surfaces `pool_state`. A connection broken by host-key rejection shows `pool_state: "broken"` and `reachable: false`. No change needed.

**`get_node_info(refresh=True)`:** Already returns `{"error": "connection_not_open", "name": name}` when `ensure_connection_open` returns None. No change needed.

Both surfaces correctly convey that the connection is unhealthy. The specific cause is in the logs. This is sufficient for this slice.

### Q9: `remove_node` and `known_hosts`

`remove_node` does **not** delete `known_hosts` entries. Rationale: host-key trust is endpoint-scoped. Removing a node removes its registry/pool entry only. The trust entry remains for potential re-use.

### Q10: Reverse tunnel scope boundary

`TunnelConnection` is not changed in this slice. It retains `AutoAddPolicy()`. When reverse tunnel lifecycle is implemented, it will be subject to a separate host-key hardening pass. Document the deferred state clearly.

---

## Architecture Flow

### Bootstrap (`add_node`) — New Flow

```
1. Validate input (mode guard, duplicate guard)
2. Password connect → pw_client (AutoAddPolicy — operator-initiated, acceptable)
3. Capture server host key from pw_client transport
4. Write host key to /data/ssh/known_hosts (idempotent: skip if already present and matching)
5. Read agent public key
6. Install public key to ~/.ssh/authorized_keys via SFTP
7. Close pw_client
8. Add ConnectionConfig(known_hosts_path=/data/ssh/known_hosts) to pool
9. ensure_connection_open → uses RejectPolicy + known_hosts → validates trust
10. If conn is None → rollback + {"error": "key_auth_failed"}
11. Commit to registry with known_hosts_path
12. Return {"status": "added", "validated": True}
```

### Pooled Connection (`DirectConnection.open()`) — New Behavior

```
known_hosts_path set → RejectPolicy + load_host_keys → strict validation
known_hosts_path None → AutoAddPolicy (legacy backward compat)
```

---

## Layer Responsibility Table

| Responsibility | Layer | Method/Location |
|---|---|---|
| `/data/ssh` directory as SSH state root | `run_agent.py` | `--ssh-dir` default, passed to `AgentIdentityService` and as `known_hosts_path` |
| `known_hosts` path derivation | `run_agent.py` | `known_hosts_path = os.path.join(ssh_dir, "known_hosts")` |
| `known_hosts` file initialization (ensure exists) | `run_agent.py` | `os.makedirs(ssh_dir, exist_ok=True); touch known_hosts if missing` |
| Capture server host key during bootstrap | `NodeService.add_node()` | `transport.get_remote_server_key()` after pw_client.connect |
| Write host key to `known_hosts` | `NodeService.add_node()` | `paramiko.HostKeys.add()` + `.save()` |
| Strict host-key enforcement on pooled connections | `DirectConnection.open()` | `RejectPolicy()` + `load_host_keys()` if `known_hosts_path` set |
| `ConnectionConfig.known_hosts_path` field | `ConnectionConfig` | New optional field, default None |
| `NodeConfig` stores `known_hosts_path` | `NodeConfig` | New optional field, mirroring `ConnectionConfig` |
| Test `known_hosts` injection | Test fixtures | `tmp_path / "known_hosts"`, `_write_known_hosts()` helper |

---

## Files to Modify

| File | Change |
|---|---|
| [`app.py`](../app.py) | Add `--ssh-dir` arg (default `/data/ssh`); deprecate `--agent-key-dir` as alias; pass `known_hosts_path` to `run_agent()` |
| [`agent/run_agent.py`](../agent/run_agent.py) | Accept `ssh_dir` / `known_hosts_path`; ensure `/data/ssh` dir and `known_hosts` file exist; pass `known_hosts_path` to `NodeService` |
| [`agent/connectionpool/config_loader.py`](../agent/connectionpool/config_loader.py) | Add `known_hosts_path: Optional[str] = None` to `ConnectionConfig` |
| [`agent/connectionpool/connection.py`](../agent/connectionpool/connection.py) | `BaseConnection.__init__` reads `known_hosts_path`; `DirectConnection.open()` uses `RejectPolicy` + `load_host_keys` when set |
| [`agent/nodes/models.py`](../agent/nodes/models.py) | Add `known_hosts_path: Optional[str] = None` to `NodeConfig` |
| [`agent/nodes/service.py`](../agent/nodes/service.py) | `__init__` accepts `known_hosts_path`; `add_node()` captures server key and writes to `known_hosts`; builds `ConnectionConfig` and `NodeConfig` with `known_hosts_path` |
| [`tests/sshd_fixture.py`](../tests/sshd_fixture.py) | Add `host_key_path` to `SpawnedSSHD` dataclass; add `_write_known_hosts()` helper |
| [`tests/agent/nodes/conftest.py`](../tests/agent/nodes/conftest.py) | Update `make_service()` to accept `known_hosts_path`; update `make_mock_identity_service()` if needed |
| [`tests/functional/test_connection_functional.py`](../tests/functional/test_connection_functional.py) | Add strict known_hosts validation tests |
| [`tests/agent/nodes/test_node_lifecycle.py`](../tests/agent/nodes/test_node_lifecycle.py) | Add unit tests for `add_node` known_hosts write path |
| [`tests/agent/connectionpool/test_connection.py`](../tests/agent/connectionpool/test_connection.py) | Add `DirectConnection` tests for `RejectPolicy` + `known_hosts` enforcement |
| [`docs/SECURITY.md`](../docs/SECURITY.md) | Document host-key trust model, endpoint-scope caveat, operator recovery |
| [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) | Update connection trust model section |

---

## Test Matrix

### Unit Tests

| Test | Setup | Expected |
|---|---|---|
| `test_direct_connection_uses_reject_policy_when_known_hosts_set` | `ConnectionConfig(known_hosts_path=path)`, mock SSH | `RejectPolicy` set, `load_host_keys(path)` called |
| `test_direct_connection_uses_auto_add_policy_when_known_hosts_none` | `ConnectionConfig(known_hosts_path=None)` | `AutoAddPolicy` set |
| `test_add_node_writes_host_key_to_known_hosts` | all steps mocked; `add_node` called with `known_hosts_path` | `HostKeys.save()` called with correct host+key entry |
| `test_add_node_host_key_written_before_key_validation` | mock pw_client, mock `get_remote_server_key` | known_hosts written before `pool.add_connection()` called |
| `test_add_node_idempotent_known_hosts_write` | key already present in known_hosts | `HostKeys.save()` not called a second time (or same entry not duplicated) |
| `test_add_node_known_hosts_path_in_connection_config` | successful add_node | `ConnectionConfig` passed to `pool.add_connection` has `known_hosts_path` set |
| `test_add_node_known_hosts_path_in_node_config` | successful add_node | `NodeConfig` in registry has `known_hosts_path` set |
| `test_node_config_known_hosts_path_field` | `NodeConfig(known_hosts_path="/data/ssh/known_hosts")` | field accepted and stored |
| `test_connection_config_known_hosts_path_default_none` | `ConnectionConfig(...)` without `known_hosts_path` | `known_hosts_path is None` |

### Functional Tests

| Test | Setup | Expected |
|---|---|---|
| `test_direct_connection_succeeds_with_matching_known_hosts` | `spawn_sshd`; write fixture host key to tmp `known_hosts`; connect with `known_hosts_path` set | Connection opens successfully |
| `test_direct_connection_fails_with_empty_known_hosts` | `spawn_sshd`; empty `known_hosts`; `RejectPolicy`; connect | Open fails; connection state `BROKEN` |
| `test_direct_connection_fails_when_host_key_changes` | write wrong key to `known_hosts`; connect | Open fails; `BadHostKeyException`; state `BROKEN` |
| `test_add_node_writes_host_key_and_validates` | `spawn_sshd_password`; `add_node` with `known_hosts_path` set | Returns `validated: True`; `known_hosts` contains server key; key-based connection uses strict policy |
| `test_add_node_key_validation_uses_strict_policy` | After bootstrap; mutate `known_hosts` to wrong key; try `ensure_connection_open` | Returns None (strict validation enforced) |

---

## Migration Note for `entrypoint.sh`

[`entrypoint.sh`](../entrypoint.sh) currently passes `--connection-config` but not `--agent-key-dir`. The new default of `/data/ssh` applies automatically when `--ssh-dir` is not specified. For existing deployments with `/data/keys` volume-mounted, the operator should either:
1. Add `--ssh-dir /data/keys` to the entrypoint (note: `known_hosts` would then live at `/data/keys/known_hosts`), or
2. Copy keypair files from `/data/keys/` to `/data/ssh/` on the volume.

Document this in a migration note in [`docs/DEVELOPER.md`](../docs/DEVELOPER.md).

---

## Non-Goals for This Slice

- Reverse tunnel lifecycle (`TunnelConnection` keeps `AutoAddPolicy`)
- `sshd` tunnel intake
- Host-key accept/reject/reset MCP tools
- Custom host-key database
- Production image split for `sshbootstrap`
- End-to-end `entrypoint.sh` migration validation
- Automatic migration of `/data/keys` to `/data/ssh` at startup

---

## Validation Expectations

After implementation, the following must pass:

```bash
pytest -m "not functional and not integration" -q   # zero failures, zero warnings
pytest -m functional -q                              # zero failures, zero warnings
```

Specific behaviors proven:
- Pooled direct connection succeeds with matching `known_hosts` entry
- Pooled direct connection fails (state: BROKEN) when host key missing from `known_hosts`
- Pooled direct connection fails (state: BROKEN) when host key in `known_hosts` differs
- `add_node` writes host key to `known_hosts` before key-based validation
- `add_node` validates key-based connection using strict `known_hosts` policy
- Multiple nodes sharing same host:port use the same `known_hosts` entry (shared trust)
- All tests use `tmp_path`-scoped `known_hosts`, not developer `~/.ssh/known_hosts`
- Warnings remain clean (zero new warnings introduced)

---

## Deferred Work

- Reverse tunnel host-key hardening (future slice after reverse tunnel lifecycle)
- Structured `last_error` field on `Connection` for surfacing `BadHostKeyException` specifically
- `/data/ssh/known_hosts` entry removal on `remove_node` (currently: no deletion, by design)
- Production image split (`sshbootstrap` stays in both images until image split slice)
- OpenSSH `sshd` as a controlled process for reverse tunnel intake (future reverse tunnel slice)
