# Direct Node Completion Slice

## Context Summary

This slice completes four deferred stubs in the `mcp-ssh-gateway` codebase. All phases operate on the existing layered architecture:

- **`NodeService`** ([`agent/nodes/service.py`](../agent/nodes/service.py)) — business logic, owns guard ordering
- **`ConnectionPool`** ([`agent/connectionpool/pool.py`](../agent/connectionpool/pool.py)) — connection lifecycle
- **`NodeHandshakeService`** ([`agent/nodes/handshake.py`](../agent/nodes/handshake.py)) — fact collection, never raises
- **`NodeRegistry`** ([`agent/nodes/registry.py`](../agent/nodes/registry.py)) — config + cache store
- **`DirectConnection` / `TunnelConnection`** ([`agent/connectionpool/connection.py`](../agent/connectionpool/connection.py)) — Paramiko transport
- **`AgentIdentityService`** ([`agent/identity/service.py`](../agent/identity/service.py)) — agent keypair access

Current confirmed stubs:
- `get_node_info(refresh=True)` → returns `"refresh_note": "live refresh not yet implemented"` *(to be replaced)*
- `enable_node(validate=True)` → returns `"validate_note": "validation not yet implemented"`
- `add_node(...)` → returns `"status": "bootstrap_not_implemented"`
- `run_command` / `upload_file` in MCP handlers execute on the gateway host (not nodes) — **Phase 1 already complete**

> Host-key verification hardening is deferred to a future slice. Until that slice is implemented, `AutoAddPolicy` remains active for pooled connections.

---

## Design Constraints

The following constraints are absolute and must be respected in all implementation and test work derived from this plan:

- `refresh=True` is an **explicit manual refresh** triggered by the caller, not a live or periodic mechanism
- **Refresh requires an explicit target** (a named node). If `refresh=True` is called without a node name, return `{"error": "refresh_target_required"}`. Node facts are low-volatility; refresh should be purposeful and bounded.
- **`get_node_info(refresh=True)` guard sequence distinguishes `not_in_pool` from `connection_not_open`**, matching `ensure_node_ready` behavior
- **Tests must not mutate the devcontainer user password under any circumstances**
- **Functional password-bootstrap tests require a fully isolated test user or are deferred to a later slice**

---

## Phase Ordering

```
Phase 1 — Remove legacy local tools (run_command, upload_file)   ✅ COMPLETE
Phase 2 — get_node_info(name, refresh=True) — named manual refresh only
Phase 3 — enable_node(validate=True)
Phase 4 — add_node direct bootstrap with unit tests (no unsafe password fixture)
```

**Rationale for ordering:**
- **Phase 1 complete:** Legacy tools removed. Namespace is clean.
- **Phase 2 before Phase 3:** `get_node_info(refresh=True)` and `enable_node(validate=True)` share the same handshake pattern; implementing Phase 2 first lets Phase 3 reuse the tested pattern.
- **Phase 4 last:** Most complex phase; benefits from all prior patterns being stable.

---

## Phase 1: Remove Legacy Local Tools ✅ COMPLETE

`run_command` and `upload_file` have been removed from [`agent/mcp_handlers.py`](../agent/mcp_handlers.py). Node-oriented equivalents are fully implemented and tested: `run_command_on_node`, `upload_file_to_node`, `download_file_from_node`.

**Validation:** `run_command` and `upload_file` are not present in the registered MCP tool list. `run_command_on_node`, `upload_file_to_node`, `download_file_from_node` remain present.

---

## Phase 2: `get_node_info(name, refresh=True)` — Named Manual Refresh Only

### Design

`refresh=True` is an **explicit manual refresh** — the caller explicitly requests that cached node facts be refreshed on demand. There is no background refresh, no automatic periodic refresh, and no refresh on every status call.

```
get_node_info(refresh=False) = read cached info only (no handshake)
get_node_info(refresh=True)  = explicitly refresh cached node facts on demand (single named node)
```

#### Named Manual Refresh: `get_node_info(name="node-a", refresh=True)`

Guard sequence — each failure short-circuits with a structured error dict:

```
1. name is None and refresh=True → {"error": "refresh_target_required",
                                     "reason": "Specify a node name when refresh=true"}
2. registry.exists(name)          → {"error": "node not found", "name": name}
3. config.enabled                 → {"error": "node_disabled", "name": name}
4. conn_obj = pool.get_connection(name)
   if conn_obj is None            → {"error": "not_in_pool", "name": name}
5. conn = pool.ensure_connection_open(name)
   if conn is None                → {"error": "connection_not_open", "name": name}
6. handshake_service.run(conn)    → facts dict (empty on failure — see below)
7. if facts non-empty:
       registry.update_cache(name, NodeInfoCache(facts, collected_at=now))
8. re-read (config, cache) from registry
9. return node entry
```

#### Handshake Failure Signaling

If `handshake_service.run()` returns `{}` (empty facts), this is **not** a soft success. The cache update is skipped (stale cache preserved). The response must clearly indicate failure and preserve the stale cache in the `info` field:

```json
{
  "nodes": [
    {"name": "node-a", "enabled": true, "pool_state": "open", "info": {"...stale cache..."}}
  ],
  "refreshed": [],
  "refresh_failed": {
    "node-a": "handshake_returned_empty"
  }
}
```

Do **not** return a response that looks like a successful refresh. Use `refresh_failed` as the key — not `refresh_note`. The public field for node facts is `info`, not `node_facts`.

#### Refresh Without a Named Target: Not Supported

`get_node_info(name=None, refresh=True)` returns immediately:

```json
{
  "error": "refresh_target_required",
  "reason": "Specify a node name when refresh=true"
}
```

Refresh requires an explicit target. The gateway does not provide an implicit refresh-all behavior because node facts are low-volatility and refresh should be intentional.

If a refresh-all operation is ever needed, it must be a separate explicitly named tool (e.g., `refresh_all_node_info`), not an overload of this parameter. That tool is **not** in scope for this plan.

**Purposeful refresh triggers in this gateway:**
- Explicit `get_node_info(name, refresh=True)` call
- `enable_node(validate=True)` — validates and refreshes that named node
- `add_node` after successful bootstrap
- First execution/readiness check when cache is empty (`ensure_node_ready`)

After reconnect, handshake runs only if cache is empty — not automatically on every reconnect.

#### Non-Refresh Path (`refresh=False`)

No changes to current behavior: return stale cache as-is. Remove the `refresh_note` stub key entirely (it will no longer appear on `refresh=False`).

**Success response shape:**
```json
{
  "nodes": [
    {"name": "node-a", "enabled": true, "pool_state": "open", "info": { ... }}
  ],
  "refreshed": ["node-a"]
}
```

**Error response shapes:**
```json
{"error": "refresh_target_required", "reason": "Specify a node name when refresh=true"}
{"error": "node not found", "name": "node-a"}
{"error": "node_disabled", "name": "node-a"}
{"error": "not_in_pool", "name": "node-a"}
{"error": "connection_not_open", "name": "node-a"}
```

**Handshake failure response shape:**
```json
{
  "nodes": [
    {"name": "node-a", "enabled": true, "pool_state": "open", "info": {"...stale cache or null..."}}
  ],
  "refreshed": [],
  "refresh_failed": {
    "node-a": "handshake_returned_empty"
  }
}
```

### Layer Responsibility Table — Phase 2

| Step | Responsible Layer | Method |
|---|---|---|
| Refresh-without-name rejection | `NodeService` | inline guard on `name is None and refresh` |
| Registry existence check | `NodeService` | `registry.exists(name)` |
| Enabled guard | `NodeService` | `config.enabled` field check |
| Pool presence guard | `ConnectionPool` | `pool.get_connection(name)` |
| Connection open / re-open | `ConnectionPool` | `pool.ensure_connection_open(name)` |
| Fact collection | `NodeHandshakeService` | `handshake_service.run(conn, timeout=10)` |
| Cache write (non-empty only) | `NodeRegistry` | `registry.update_cache(name, NodeInfoCache(...))` |
| Response assembly | `NodeService` | `_node_entry_for_info(config, cache)` |

### Files Modified — Phase 2

| File | Change |
|---|---|
| [`agent/nodes/service.py`](../agent/nodes/service.py) | Replace stub in `get_node_info()` with real manual refresh logic |
| [`tests/agent/nodes/test_node_status_info.py`](../tests/agent/nodes/test_node_status_info.py) | New unit test cases |
| [`tests/functional/test_node_service_functional.py`](../tests/functional/test_node_service_functional.py) | New functional test cases |

### Test Matrix — Phase 2

#### Unit Tests (mock-based)

| Test | Setup | Expected |
|---|---|---|
| `test_refresh_single_node_success` | node exists, enabled, pool returns conn obj, conn open, handshake returns non-empty facts | response has `nodes`, `refreshed: ["node-a"]`, `info` populated |
| `test_refresh_single_node_not_found` | registry has no node | `{"error": "node not found", "name": "node-a"}` |
| `test_refresh_single_node_disabled` | node exists, `enabled=False` | `{"error": "node_disabled", "name": "node-a"}` |
| `test_refresh_single_node_not_in_pool` | enabled, `pool.get_connection` returns `None` | `{"error": "not_in_pool", "name": "node-a"}` |
| `test_refresh_single_node_connection_not_open` | in pool, `ensure_connection_open` returns `None` | `{"error": "connection_not_open", "name": "node-a"}` |
| `test_refresh_single_node_handshake_empty` | enabled, conn open, handshake returns `{}` | response has `refresh_failed: {"node-a": "handshake_returned_empty"}`, no cache update, stale `info` preserved |
| `test_refresh_without_name_returns_error` | `name=None`, `refresh=True` | `{"error": "refresh_target_required", "reason": "Specify a node name when refresh=true"}` |
| `test_no_refresh_returns_stale_no_refresh_failed` | node with stale cache, `refresh=False` | no `refresh_failed` key in response; no `refresh_note` key in response |
| `test_refresh_handshake_empty_returns_stale_cache` | pre-populated stale cache, handshake returns `{}` | `info` contains stale data, `refresh_failed` present |
| `test_refresh_cache_updated_on_non_empty_handshake` | handshake returns non-empty facts | `registry.update_cache` called; response `info` reflects new facts |

#### Functional Tests (live sshd)

| Test | Setup | Expected |
|---|---|---|
| `test_refresh_single_node_populates_cache` | `spawn_sshd` fixture, pool open, empty cache | after `get_node_info(name, refresh=True)`, cache is populated; response `info` dict non-empty |
| `test_refresh_single_node_updates_stale_cache` | pre-populate cache with stale facts, then refresh | cache replaced with fresh facts from handshake |

---

## Phase 3: `enable_node(validate=True)`

### Design

#### `validate=False` (Complete Existing Behavior — Remove Stub Note)

```
1. registry.exists(name)     → {"error": "node not found", "name": name}
2. replace(config, enabled=True) → registry.update_config(name, updated)
3. pool.enable_connection(name)  # clears disabled mark, monitor resumes
4. return {"status": "enabled", "name": name}
```

No change in observable behavior other than removing the `validate_note` stub key.

#### `validate=True` (New Behavior)

```
1. registry.exists(name)          → {"error": "node not found", "name": name}
2. replace(config, enabled=True)  → registry.update_config(name, updated)
3. pool.enable_connection(name)
4a. conn_obj = pool.get_connection(name)
    if conn_obj is None:
        return {"status": "enabled", "name": name, "validated": false, "error": "not_in_pool"}
4b. conn = pool.ensure_connection_open(name)
    if conn is None:
        return {"status": "enabled", "name": name, "validated": false, "error": "connection_not_open"}
5. facts = handshake_service.run(conn, timeout=10)
6. if facts:
       registry.update_cache(name, NodeInfoCache(facts, collected_at=now))
       return {"status": "enabled", "name": name, "validated": true}
7. else:
       return {"status": "enabled", "name": name, "validated": false, "error": "handshake_failed"}
```

**Critical constraint:** The node is **not** reverted to disabled on validation failure. The node is enabled regardless of the `validated` outcome — validation is a probe, not a gate. The operator explicitly enabled the node; the service must not silently undo that intent.

**Success response shape:**
```json
{"status": "enabled", "name": "node-a", "validated": true}
```

**Failure response shapes:**
```json
{"status": "enabled", "name": "node-a", "validated": false, "error": "not_in_pool"}
{"status": "enabled", "name": "node-a", "validated": false, "error": "connection_not_open"}
{"status": "enabled", "name": "node-a", "validated": false, "error": "handshake_failed"}
```

### Layer Responsibility Table — Phase 3

| Step | Responsible Layer | Method |
|---|---|---|
| Registry existence + enabled mark | `NodeService` | `registry.exists()`, `registry.update_config()` |
| Pool disabled-mark clear | `ConnectionPool` | `pool.enable_connection(name)` |
| Pool presence guard | `ConnectionPool` | `pool.get_connection(name)` |
| Connection open attempt | `ConnectionPool` | `pool.ensure_connection_open(name)` |
| Handshake probe | `NodeHandshakeService` | `handshake_service.run(conn, timeout=10)` |
| Cache update on success | `NodeRegistry` | `registry.update_cache(name, ...)` |
| Response assembly | `NodeService` | inline in `enable_node()` |

### Files Modified — Phase 3

| File | Change |
|---|---|
| [`agent/nodes/service.py`](../agent/nodes/service.py) | Replace stub in `enable_node()` with real validation logic |
| [`tests/agent/nodes/test_node_lifecycle.py`](../tests/agent/nodes/test_node_lifecycle.py) | New unit test cases |
| [`tests/functional/test_node_service_functional.py`](../tests/functional/test_node_service_functional.py) | New functional test cases |

### Test Matrix — Phase 3

#### Unit Tests (mock-based)

| Test | Setup | Expected |
|---|---|---|
| `test_enable_no_validate_removes_stub_note` | valid node | response has no `validate_note` key |
| `test_enable_validate_false_does_not_open` | valid node | `pool.ensure_connection_open` NOT called |
| `test_enable_validate_true_success` | node exists, conn open, handshake returns facts | `{"status": "enabled", "name": "node-a", "validated": true}` |
| `test_enable_validate_true_not_in_pool` | node exists in registry, not in pool | `{"validated": false, "error": "not_in_pool"}` |
| `test_enable_validate_true_connection_not_open` | node in pool, `ensure_connection_open` → None | `{"validated": false, "error": "connection_not_open"}` |
| `test_enable_validate_true_handshake_fails` | conn open, handshake returns `{}` | `{"validated": false, "error": "handshake_failed"}` |
| `test_enable_validate_true_does_not_revert_on_failure` | connection fails | `status` is still `"enabled"`, `registry.get(name).enabled is True` |
| `test_enable_not_found` | name not in registry | `{"error": "node not found", "name": name}` |
| `test_enable_validate_true_updates_cache_on_success` | handshake returns facts | `registry.update_cache` called with fresh `NodeInfoCache` |

#### Functional Tests (live sshd)

| Test | Setup | Expected |
|---|---|---|
| `test_enable_validate_true_succeeds_against_live_sshd` | `spawn_sshd`, node previously disabled | response `validated: true`, registry cache populated |
| `test_enable_validate_true_fails_when_no_pool_entry` | node in registry but not pool | `validated: false`, `error: "not_in_pool"`, node still enabled |

---

## Phase 4: `add_node` Bootstrap (Direct Mode Only)

### Service Wiring

`NodeService.__init__` must accept `AgentIdentityService` as an explicit constructor parameter:

```python
class NodeService:
    def __init__(
        self,
        registry: NodeRegistry,
        pool: ConnectionPool,
        handshake_service: NodeHandshakeService,
        agent_identity_service: AgentIdentityService,
    ):
        ...
```

**Preferred wiring:** `NodeService(registry, pool, handshake_service, agent_identity_service)`

**Alternative:** If `add_node` bootstrap logic grows large, extract to a dedicated `NodeOnboardingService(registry, pool, agent_identity_service)`. `NodeService.add_node` then delegates to that service. The handler layer must keep delegating only — identity access must not be hidden inside handlers.

```
If add_node implementation becomes large, extract bootstrap logic to NodeOnboardingService.
NodeService.add_node should then delegate to that service.
```

### Design

#### Rejected Inputs (Immediate Returns)

```
mode == "tunnel"         → {"error": "unsupported_mode", "mode": "tunnel",
                             "reason": "assisted tunnel onboarding is not implemented"}
name already in registry → {"error": "node_already_exists", "name": name}
```

#### Password Bootstrap Flow

```
Step 1: VALIDATE INPUT
    - Reject mode == "tunnel" (see above)
    - Reject if registry.exists(name)

Step 2: PASSWORD CONNECT (one-shot, not pooled)
    pw_client = SSHClient()
    pw_client.set_missing_host_key_policy(AutoAddPolicy())  # acceptable: operator-initiated, not background
    pw_client.connect(host, port=port, username=username,
                      password=password,        # only reference to password
                      look_for_keys=False,       # no key fallback
                      allow_agent=False)         # no agent fallback
    # password is only passed to Paramiko connect;
    # password is never logged, never stored, never returned,
    # never copied into registry/pool/config/cache

Step 3: READ AGENT PUBLIC KEY
    pub_key_str = agent_identity_service.get_identity().public_key  # "ssh-ed25519 AAAA..."

Step 4: APPEND TO authorized_keys VIA SFTP
    sftp = pw_client.open_sftp()
    home = sftp.normalize(".")              # expands to absolute home path
    ssh_dir = home + "/.ssh"
    auth_keys_path = ssh_dir + "/authorized_keys"

    try:
        ...  # all SFTP operations
    finally:
        sftp.close()

    # Ensure ~/.ssh exists with correct permissions
    try:
        sftp.stat(ssh_dir)
    except FileNotFoundError:
        sftp.mkdir(ssh_dir)
        sftp.chmod(ssh_dir, 0o700)

    # Read existing content (may not exist)
    try:
        with sftp.open(auth_keys_path, "r") as f:
            existing = f.read().decode()
    except FileNotFoundError:
        existing = ""

    # Idempotent append: only add if key not already present
    if pub_key_str not in existing:
        new_content = existing.rstrip("\n") + "\n" + pub_key_str + "\n"
        with sftp.open(auth_keys_path, "w") as f:
            f.write(new_content.encode())
        sftp.chmod(auth_keys_path, 0o600)

Step 5: CLOSE PASSWORD CONNECTION
    pw_client.close()
    # password leaves scope here — no reference survives

Step 6: VALIDATE KEY-BASED CONNECTION
    conn_config = ConnectionConfig(name=name, host=host, port=port,
                                   user=username,
                                   id_file=agent_identity_service.get_identity().private_key_path,
                                   mode="direct")
    pool.add_connection(conn_config)         # new pool method — see below
    conn = pool.ensure_connection_open(name)
    if conn is None:
        pool.remove_connection(name)         # rollback
        return {"error": "key_auth_failed", "name": name, "step": "key_validation"}

Step 7: COMMIT TO REGISTRY
    node_config = NodeConfig(name=name, mode="direct", enabled=True,
                              host=host, port=port, user=username,
                              id_file=agent_identity_service.get_identity().private_key_path)
    try:
        registry.add(node_config)
    except ValueError:
        pool.remove_connection(name)         # rollback
        return {"error": "node_already_exists", "name": name}

Step 8: RETURN SUCCESS
    return {"status": "added", "name": name, "host": host, "port": port, "validated": true}
```

#### Cleanup / Rollback Contract (`finally` blocks)

All resource cleanup must occur in `finally` blocks, not relying on happy-path ordering:

```python
sftp = None
pw_client = None
pool_added = False
try:
    # Step 2: password connect
    pw_client = SSHClient()
    ...
    # Step 4: SFTP
    sftp = pw_client.open_sftp()
    ...
    sftp.close()
    sftp = None
    # Step 5: close pw_client
    pw_client.close()
    pw_client = None
    # Step 6: add to pool + validate
    pool.add_connection(conn_config)
    pool_added = True
    conn = pool.ensure_connection_open(name)
    if conn is None:
        return {"error": "key_auth_failed", ...}
    # Step 7: registry commit
    ...
except Exception:
    ...  # structured error returns
finally:
    if sftp is not None:
        try: sftp.close()
        except Exception: pass
    if pw_client is not None:
        try: pw_client.close()
        except Exception: pass
    # pool rollback only if pool was added but registry commit did not succeed
```

Registry remains unchanged unless Step 7 (validation + registry commit) succeeds. Pool entry is rolled back via `pool.remove_connection()` on any failure after Step 6.

#### `add_node` AutoAddPolicy Compatibility Note

Phase 4 `add_node` creates `ConnectionConfig` and calls `pool.add_connection(config)`. The pooled connection will use `AutoAddPolicy` until the host-key hardening slice (deferred to a future slice) is implemented. No `known_hosts` interaction is required in Phase 4. This is the same trust model as the one-shot password connection — both are operator-initiated actions.

#### New Pool Method: `pool.add_connection(config: ConnectionConfig) → None`

This method must be added to [`agent/connectionpool/pool.py`](../agent/connectionpool/pool.py):

```python
def add_connection(self, config: ConnectionConfig) -> None:
    """Add a new connection to the pool without opening it.

    Thread-safe. Raises ValueError if a connection with the same name already exists.
    Clears any disabled state for this name to ensure the monitor does not skip it.
    """
    with self.lock:
        for conn in self.connections:
            if conn.name == config.name:
                raise ValueError(f"Connection already in pool: {config.name!r}")
        self._disabled_names.discard(config.name)   # clear any stale disabled state
        connection = Connection(config)
        self.connections.append(connection)
```

The `self._disabled_names.discard(config.name)` call inside the lock ensures a previously disabled/removed/re-added node name is not skipped by the monitor.

#### Why SFTP for `authorized_keys`, Not Exec

| Criterion | SFTP | exec |
|---|---|---|
| Shell injection risk | None — SFTP is a file protocol | High — `echo "key" >> file` can fail on keys with special chars |
| Idempotency check | Read-then-write in Python, safe string comparison | Harder to implement safely in shell |
| Error handling | Granular Python exceptions per operation | One combined shell exit code |
| `~` expansion | `sftp.normalize(".")` gives absolute home path | Relies on shell expansion |
| Directory creation | Explicit `mkdir`+`chmod` calls | Requires `mkdir -p` shell + `chmod` |

SFTP is the clear choice.

#### Credential Safety Contract

- `password` is only passed to Paramiko `connect()`; it is never logged, never stored, never returned, never copied into registry/pool/config/cache.
- The one-shot `pw_client` is closed and dereferenced; after that, no reference to the password exists.
- `mcp_handlers.py` already masks the password in its debug log: it must log `mode=` but not `password=`.

#### Error Contract Table — `add_node` Bootstrap

| Step | Condition | Error Key | Extra Fields |
|---|---|---|---|
| Input validation | `mode == "tunnel"` | `unsupported_mode` | `mode`, `reason` |
| Input validation | `registry.exists(name)` before start | `node_already_exists` | `name` |
| Step 2 | Paramiko connection fails (auth, network, timeout) | `password_connect_failed` | `name`, `step: "password_connect"` |
| Step 4 | SFTP open fails | `sftp_open_failed` | `name`, `step: "authorized_keys_write"` |
| Step 4 | `authorized_keys` write fails | `authorized_keys_write_failed` | `name`, `step: "authorized_keys_write"` |
| Step 6 | `pool.ensure_connection_open` returns None | `key_auth_failed` | `name`, `step: "key_validation"` |
| Step 7 | `registry.add` raises `ValueError` (race) | `node_already_exists` | `name` |

On any failure from Step 2 onward through Step 7: registry remains unchanged, pool is rolled back (connection removed if it was added), SFTP and pw_client closed in `finally`.

#### Test Isolation Constraint for Password Bootstrap

**Tests must not mutate the devcontainer user password.** The proposed `spawn_sshd_password` fixture using `passwd -d $(whoami)` is unsafe: it mutates the real devcontainer user account and does not restore state. It is **not** included in this plan.

Test coverage is structured as follows:
- **Primary test path:** Strong unit tests with mocked Paramiko (covers all steps and error branches)
- **Functional password-bootstrap test:** Deferred unless a fully isolated test user can be created (Option B: separate temp Unix user with teardown). If that is too complex, defer entirely (Option C).
- The `@pytest.mark.requires_password_sshd` marker may be introduced for future use, but no test using it will be implemented in this plan without a fully isolated test user.

Do **not** use `passwd -d $(whoami)` or any equivalent in any test fixture.

### Layer Responsibility Table — Phase 4

| Step | Responsible Layer | Method/Object |
|---|---|---|
| Input validation | `NodeService.add_node()` | inline guard |
| Password SSH connection | `NodeService.add_node()` | one-shot `paramiko.SSHClient` |
| Public key retrieval | `AgentIdentityService` | `get_identity().public_key` |
| authorized_keys append | `NodeService.add_node()` | one-shot SFTP via password `pw_client` |
| Pool entry creation | `ConnectionPool` | `pool.add_connection(config)` (new) |
| Key-based validation | `ConnectionPool` | `pool.ensure_connection_open(name)` |
| Pool rollback on failure | `ConnectionPool` | `pool.remove_connection(name)` |
| Registry commit | `NodeRegistry` | `registry.add(node_config)` |
| Private key path retrieval | `AgentIdentityService` | `get_identity().private_key_path` |

### Files Modified — Phase 4

| File | Change |
|---|---|
| [`agent/nodes/service.py`](../agent/nodes/service.py) | Replace `add_node` stub with full bootstrap logic; add `agent_identity_service` to `__init__` |
| [`agent/connectionpool/pool.py`](../agent/connectionpool/pool.py) | Add `add_connection(config)` method with `_disabled_names.discard` |
| [`tests/agent/nodes/test_node_lifecycle.py`](../tests/agent/nodes/test_node_lifecycle.py) | New unit tests for `add_node` bootstrap (mocked Paramiko) |

### Test Matrix — Phase 4

#### Unit Tests (mock-based — primary coverage path)

| Test | Mock Setup | Expected |
|---|---|---|
| `test_add_node_tunnel_mode_rejected` | mode="tunnel" | `{"error": "unsupported_mode", "mode": "tunnel"}` |
| `test_add_node_already_exists` | `registry.exists` returns True | `{"error": "node_already_exists", "name": name}` |
| `test_add_node_password_connect_fails` | `SSHClient.connect` raises `AuthenticationException` | `{"error": "password_connect_failed", ...}`, registry unchanged |
| `test_add_node_authorized_keys_write_fails` | SFTP `open` raises `IOError` | `{"error": "authorized_keys_write_failed", ...}`, registry unchanged, pool unchanged |
| `test_add_node_key_auth_fails` | `ensure_connection_open` returns None | `{"error": "key_auth_failed", ...}`, `pool.remove_connection` called, registry unchanged |
| `test_add_node_success` | all steps succeed | `{"status": "added", "name": name, "validated": true}`, registry has node, pool has connection |
| `test_add_node_idempotent_authorized_keys` | key already in existing content | SFTP write NOT called (no duplication) |
| `test_add_node_ssh_dir_missing` | `sftp.stat` raises `FileNotFoundError` for `.ssh` | `sftp.mkdir` and `sftp.chmod` called before write |
| `test_add_node_password_never_logged` | capture logging output | no call to any logger contains the password string |
| `test_add_node_pool_rollback_on_key_auth_failure` | key auth fails | `pool.get_connection(name)` returns None after failure |
| `test_add_node_sftp_closed_in_finally` | SFTP open succeeds, write fails | `sftp.close()` called despite write failure |
| `test_add_node_pw_client_closed_in_finally` | connect succeeds, SFTP fails | `pw_client.close()` called despite SFTP failure |

#### Functional Tests

Functional password-bootstrap tests are **deferred**. They require a fully isolated test user with proper teardown. Using `passwd -d $(whoami)` or equivalent is prohibited. If a safe isolated test user solution is implemented in a later slice, functional tests may be added under `@pytest.mark.requires_password_sshd`.

---

## Layer Responsibility Table (All Phases Combined)

| Operation | `NodeService` | `ConnectionPool` | `NodeHandshakeService` | `NodeRegistry` | `AgentIdentityService` |
|---|---|---|---|---|---|
| Guard: refresh without name rejected | owns | — | — | — | — |
| Guard: node exists | owns | — | — | `exists()` | — |
| Guard: node enabled | owns | — | — | — | — |
| Guard: in pool | delegates | `get_connection()` | — | — | — |
| Guard: connection open | delegates | `ensure_connection_open()` | — | — | — |
| Fact collection | delegates | — | `run(conn)` | — | — |
| Cache write | delegates | — | — | `update_cache()` | — |
| Enabled/disabled mark | delegates | `enable_connection()` / `disable_connection()` | — | `update_config()` | — |
| Password SSH connect | owns (one-shot) | — | — | — | — |
| Public key retrieval | delegates | — | — | — | `get_identity().public_key` |
| authorized_keys write | owns (via SFTP on pw_client) | — | — | — | — |
| Pool add (new) | delegates | `add_connection()` | — | — | — |
| Registry commit | delegates | — | — | `add()` | — |
| Pool rollback | delegates | `remove_connection()` | — | — | — |

---

## Delivery Plan

### Phase Execution Order

```mermaid
graph LR
    P1[Phase 1: Remove Legacy Tools -- DONE] --> P2[Phase 2: get_node_info manual refresh]
    P2 --> P3[Phase 3: enable_node validate]
    P3 --> P4[Phase 4: add_node Bootstrap]
    P4 --> HK[host-key hardening (future slice)]
```

### New Tests Per Phase

| Phase | New Unit Tests | New Functional Tests |
|---|---|---|
| Phase 1 — Legacy removal | ✅ done | ✅ done |
| Phase 2 — Manual refresh | 10 | 2 |
| Phase 3 — enable validate | 9 | 2 |
| Phase 4 — add_node bootstrap | 12 | 0 (deferred) |
| **Total (remaining)** | **31** | **4** |

### Files Modified Per Phase

| Phase | Modified Files |
|---|---|
| Phase 1 | ✅ `mcp_handlers.py`, `test_mcp_node_tools.py`, `README.md` |
| Phase 2 | `service.py`, `test_node_status_info.py`, `test_node_service_functional.py` |
| Phase 3 | `service.py`, `test_node_lifecycle.py`, `test_node_service_functional.py` |
| Phase 4 | `service.py`, `pool.py`, `test_node_lifecycle.py` |

### Documentation Updates (This Slice)

As part of this slice, the following documentation files must be updated:

| File | Change |
|---|---|
| [`docs/MCP_VALIDATION_GUIDE.md`](../docs/MCP_VALIDATION_GUIDE.md) | Remove stale tool refs (`get_status`, `get_device_info`); confirm `run_command`/`upload_file` absent; confirm node tools present; update smoke test surface |
| [`README.md`](../README.md) | Remove legacy `run_command`/`upload_file` references; list current node-scoped tools correctly; remove stale "connection/capability" era terminology |
| [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) | Remove stale `get_status`/device-era terminology; update current implementation boundary to reflect node-scoped API surface |

### Validation Command Per Phase

```bash
# Phase 2 — get_node_info manual refresh
pytest tests/agent/nodes/test_node_status_info.py -v
pytest tests/functional/test_node_service_functional.py -m functional -v -k "refresh"

# Phase 3 — enable_node validate
pytest tests/agent/nodes/test_node_lifecycle.py -v -k "enable"
pytest tests/functional/test_node_service_functional.py -m functional -v -k "validate"

# Phase 4 — add_node bootstrap (unit tests only; functional deferred)
pytest tests/agent/nodes/test_node_lifecycle.py -v -k "add_node"

# Full non-functional suite (regression gate after all phases)
pytest -m "not functional" -q --tb=short
```

---

## Key Design Decisions Summary

| Decision | Rationale |
|---|---|
| `refresh=True` is explicit manual refresh only | No background, periodic, or automatic refresh. Caller explicitly triggers cache refresh on demand. |
| Refresh requires an explicit target. Calling `refresh=True` without a node name returns `refresh_target_required`. The gateway does not provide implicit refresh-all behavior because node facts are low-volatility and refresh should be intentional. | Refresh scope must be bounded and purposeful. |
| Phase 2 guard sequence distinguishes `not_in_pool` from `connection_not_open` | Matching `ensure_node_ready` behavior. Clear error semantics for diagnostics. |
| Disabled nodes return `node_disabled` error on single-name refresh | Clear error semantics; caller should check status before requesting refresh. |
| Handshake failure sets `refresh_failed` key in response (not `refresh_note`); public field is `info` (not `node_facts`) | Unambiguous failure signal. Field name consistency with rest of API. |
| `enable_node(validate=True)` does not revert on failure | Validation is a probe, not a gate. Operator explicitly enabled the node; the service must not silently undo that intent. |
| `authorized_keys` written via SFTP, not exec | Eliminates shell injection risk; enables Python-level idempotency check and per-operation error handling. |
| `add_node` password connection uses `AutoAddPolicy` | Bootstrap is an operator-initiated, one-shot action — acceptable for initial trust establishment. Does NOT use the pooled connection path. |
| `add_node` pooled connection uses `AutoAddPolicy` until host-key hardening (deferred to a future slice) | Phase 4 compatibility note. No `known_hosts` interaction required in this slice. |
| `AgentIdentityService` injected explicitly into `NodeService.__init__` | Dependency must be visible at construction. Identity access must not be hidden inside handlers. |
| `NodeOnboardingService` extraction allowed if `add_node` grows large | Clean separation of concerns; preserves delegation-only handler pattern. |
| `pool.add_connection()` discards `_disabled_names` for that name | Ensures a re-added node is not silently skipped by the monitor. |
| `add_node` rollback uses `finally` blocks | Cleanup must not depend on happy-path sequencing. All resources closed on all failure paths. |
| Password is not referenced "exactly once" — password is only passed to Paramiko connect | Accurate safety contract: never logged, stored, returned, or copied. |
| No `spawn_sshd_password` fixture with `passwd -d` | Mutates the real devcontainer user account without restoring state. Unsafe and non-reproducible. |
| Functional password-bootstrap tests deferred | Require a fully isolated test user with teardown. Not feasible without that infrastructure. |
| Legacy `run_command` / `upload_file` fully removed (Phase 1 complete) | Gateway's purpose is node access, not gateway-host execution. `shell=True` local exec is a security footgun with no use case in a node-management gateway. |
| Phase 5 host-key hardening deferred to a future slice | Touches all connection fixtures. Keeps this slice manageable and Phase 4 `add_node` stable before hardening changes propagate. |
| `pool.add_connection()` as new method | `add_node` bootstrap needs transactional rollback semantics. Adding to pool before committing to registry enables `remove_connection()` rollback without registry involvement. |
