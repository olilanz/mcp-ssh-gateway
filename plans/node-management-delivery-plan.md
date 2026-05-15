# Node Management API — Phased Delivery Plan

Reference architecture: [`plans/node-management-api-slice.md`](node-management-api-slice.md)

---

## Phase 1 — Node model + registry + tests

### Files touched

| File | Action |
|------|--------|
| `agent/nodes/__init__.py` | Create (empty package marker) |
| `agent/nodes/models.py` | Create — `NodeConfig`, `NodeInfoCache`, `NodeRuntimeState` (DTO only) |
| `agent/nodes/registry.py` | Create — `NodeRegistry` storing `NodeConfig` + `NodeInfoCache` only |
| `tests/agent/nodes/__init__.py` | Create (empty package marker) |
| `tests/agent/nodes/test_registry.py` | Create — registry unit tests |

**Note:** Partially created files exist at `agent/nodes/models.py`, `agent/nodes/registry.py`, and `tests/agent/nodes/test_node_service.py` from a previous interrupted task. `models.py` and `registry.py` must be replaced/rewritten to match the corrected design. The old `test_node_service.py` covers registry concerns — those tests must be extracted into `test_registry.py`; `test_node_service.py` will be created fresh in Phase 3.

### Behavior delivered

- `NodeConfig` dataclass with fields: `name`, `mode`, `enabled`, `host`, `port`, `user`, `id_file`
- `NodeInfoCache` dataclass with fields: `facts`, `collected_at`
- `NodeRuntimeState` dataclass with fields: `pool_state`, `reachable`, `last_seen_at`, `last_error` — typed DTO only; explicitly never stored in registry
- `NodeRegistry` in-memory, thread-safe store of `dict[str, tuple[NodeConfig, NodeInfoCache]]`
- Full public interface: `add`, `remove`, `get`, `all`, `exists`, `update_config`, `update_cache`
- `add()` raises `ValueError` for duplicate names
- `remove()` / `get()` raise `KeyError` for unknown names

### Tests added

File: `tests/agent/nodes/test_registry.py`

| Test | What it checks |
|------|---------------|
| `test_add_and_get` | `add()` then `get()` returns matching `NodeConfig` and empty `NodeInfoCache` |
| `test_add_duplicate_raises` | Second `add()` with same name raises `ValueError` |
| `test_remove_existing` | After `remove()`, `get()` raises `KeyError` |
| `test_remove_unknown_raises` | `remove()` on unknown name raises `KeyError` |
| `test_exists_true_and_false` | `exists()` returns `True` / `False` correctly |
| `test_all_returns_all_entries` | `all()` returns all `(NodeConfig, NodeInfoCache)` tuples |
| `test_update_config` | `update_config()` replaces stored `NodeConfig` |
| `test_update_cache` | `update_cache()` replaces stored `NodeInfoCache` |
| `test_registry_does_not_store_runtime_state` | `get()` return type is a 2-tuple `(NodeConfig, NodeInfoCache)` |

### Targeted pytest command

```bash
pytest tests/agent/nodes/test_registry.py -v
```

### MCP validation step

None — no MCP surface changes in this phase.

### Completion gate

- All `test_registry.py` tests pass.
- `registry.get()` return type is confirmed as `tuple[NodeConfig, NodeInfoCache]` (two elements, no `NodeRuntimeState`).
- All pre-existing tests still pass: `pytest tests/ -v --ignore=tests/integration`

---

## Phase 2 — Pool disable/remove/enable seam + tests

### Files touched

| File | Action |
|------|--------|
| `agent/connectionpool/pool.py` | Modify — add `disable_connection`, `enable_connection`, `remove_connection`; monitor loop respects disabled/removed state |
| `tests/agent/connectionpool/test_pool.py` | Modify — add seam tests |

### Behavior delivered

- `pool.disable_connection(name: str) -> None`: closes connection, marks it disabled; monitor will not reopen it
- `pool.enable_connection(name: str) -> None`: re-enables the connection for monitor management; does not immediately open
- `pool.remove_connection(name: str) -> None`: closes connection, removes from pool entirely; raises `KeyError` if not found
- Background monitor loop checks disabled/removed state before every reconnect attempt; skips connections in disabled or removed state

### Tests added

Appended to `tests/agent/connectionpool/test_pool.py`:

| Test | What it checks |
|------|---------------|
| `test_disable_connection_closes_and_prevents_reconnect` | Disabled connection is closed; subsequent monitor iteration does not reopen it |
| `test_enable_connection_allows_monitor_to_reconnect` | After `enable_connection()`, monitor may attempt reconnect |
| `test_remove_connection_removes_from_pool` | `remove_connection()` removes entry; connection no longer in pool |
| `test_remove_connection_unknown_raises` | `remove_connection()` raises `KeyError` for unknown name |
| `test_monitor_skips_disabled_connection` | Direct monitor loop iteration leaves disabled connection closed |

### Targeted pytest command

```bash
pytest tests/agent/connectionpool/test_pool.py -v
```

### MCP validation step

None — internal pool change; not yet wired to MCP surface.

### Completion gate

- All new pool seam tests pass.
- All existing pool tests still pass.
- Monitor loop demonstrably does not reopen a disabled connection (covered by `test_monitor_skips_disabled_connection`).

---

## Phase 3 — NodeService read APIs + tests

### Files touched

| File | Action |
|------|--------|
| `agent/nodes/service.py` | Create — `NodeService` with `get_status()` and `get_node_info(name, refresh)` only |
| `tests/agent/nodes/test_node_service.py` | Create — read API tests (replaces/supersedes any prior file) |

### Behavior delivered

- `NodeService.__init__(registry: NodeRegistry, pool: ConnectionPool)`
- `get_status()`: reads all `(NodeConfig, NodeInfoCache)` from registry; queries live `ConnectionState` from pool for each node; assembles response with `pool_state` derived at call time; never copies pool state into registry
- `get_node_info(name: Optional[str], refresh: bool)`: returns configured info + cached facts + current pool state; `refresh=false` performs no SSH; `refresh=true` stubbed with note; unknown name returns `{"error": "node not found", "name": "..."}`
- `NodeRuntimeState` assembled inline — never stored

### Tests added

File: `tests/agent/nodes/test_node_service.py` (read API section)

| Test | What it checks |
|------|---------------|
| `test_get_status_empty_registry` | Returns `{"status": "ok", "nodes": []}` |
| `test_get_status_includes_node_fields` | Each node entry has `enabled`, `pool_state`, `configured`, `cached_info_available` |
| `test_get_status_pool_state_from_pool_not_registry` | `pool_state` reflects live mock pool return value, not any stored value |
| `test_get_node_info_all_nodes` | Returns list of all configured nodes |
| `test_get_node_info_single_node` | Returns only the named node |
| `test_get_node_info_unknown_node` | Returns `{"error": "node not found", "name": "..."}` |
| `test_get_node_info_refresh_false_no_ssh` | Pool's SSH methods are never called on `refresh=false` |

All tests use a real `NodeRegistry` and a mocked `ConnectionPool`. No live SSH.

### Targeted pytest command

```bash
pytest tests/agent/nodes/test_node_service.py -v -k "status or node_info"
```

### MCP validation step

None — not yet wired to MCP surface.

### Completion gate

- All read API tests in `test_node_service.py` pass.
- All Phase 1 and Phase 2 tests still pass.

---

## Phase 4 — NodeService mutation APIs + tests

### Files touched

| File | Action |
|------|--------|
| `agent/nodes/service.py` | Modify — add `enable_node`, `disable_node`, `remove_node`, `add_node` |
| `tests/agent/nodes/test_node_service.py` | Modify — add mutation tests and password safety tests using `caplog` |

### Behavior delivered

- `add_node(name, host, port, user, password, mode)`: returns `bootstrap_not_implemented`; node is **not** added to registry; password never stored, logged, or returned
- `remove_node(name)`: calls `pool.remove_connection(name)`; removes from registry; returns `{"status": "removed", "name": ...}`; unknown name returns error
- `enable_node(name, validate)`: sets `enabled=True` in registry config; calls `pool.enable_connection(name)`; returns `{"status": "enabled", "name": ...}`
- `disable_node(name)`: sets `enabled=False` in registry config; calls `pool.disable_connection(name)`; returns `{"status": "disabled", "name": ...}`

### Tests added

Appended to `tests/agent/nodes/test_node_service.py`:

| Test | What it checks |
|------|---------------|
| `test_add_node_returns_bootstrap_not_implemented` | Status is `bootstrap_not_implemented`, reason field present |
| `test_add_node_does_not_add_to_registry` | Registry `exists(name)` is `False` after `add_node` call |
| `test_add_node_result_contains_no_password` | Return value dict contains no `password` key |
| `test_add_node_password_not_in_logs` | `caplog` captures no log record containing the password string |
| `test_add_node_password_not_in_registry` | No entry in registry contains password value after call |
| `test_remove_node_removes_from_status` | Node absent from `get_status()` after `remove_node()` |
| `test_remove_node_calls_pool_remove_connection` | Mock verifies `pool.remove_connection(name)` was called (not `close()`) |
| `test_remove_node_unknown_returns_error` | Returns `{"error": "node not found", "name": "..."}` |
| `test_disable_node_marks_disabled` | `enabled=False` in `get_status()`; node still present |
| `test_disable_node_calls_pool_disable_connection` | Mock verifies `pool.disable_connection(name)` was called (not `close()`) |
| `test_enable_node_marks_enabled` | `enabled=True` in `get_status()` after `enable_node()` |
| `test_enable_node_calls_pool_enable_connection` | Mock verifies `pool.enable_connection(name)` was called |

### Targeted pytest command

```bash
pytest tests/agent/nodes/test_node_service.py -v
```

Full phase 1–4 regression:

```bash
pytest tests/agent/nodes/ tests/agent/connectionpool/test_pool.py -v
```

### MCP validation step

None — not yet wired to MCP surface.

### Completion gate

- All mutation tests pass including all `caplog` password safety tests.
- `add_node` confirmed to never add to registry.
- All prior phase tests still pass.

---

## Phase 5 — MCP handler wiring + tests

### Files touched

| File | Action |
|------|--------|
| `agent/mcp_handlers.py` | Modify — new `register_tools(mcp, node_service)` signature; implement all 6 tools with explicit typed FastMCP arguments; remove `get_device_info` |
| `agent/run_agent.py` | Modify — seed registry from pool config, construct `NodeService`, pass to `register_tools` |
| `tests/agent/test_mcp_node_tools.py` | Create — tool registration tests, response shape tests |

### Behavior delivered

- `register_tools(mcp: FastMCP, node_service: NodeService)` replaces `register_tools(mcp)`
- All 6 tools registered: `get_status`, `get_node_info`, `add_node`, `remove_node`, `enable_node`, `disable_node`
- `get_device_info` removed from registration
- All tools use explicit typed FastMCP arguments (not a `params` dict):
  ```python
  @mcp.tool()
  async def disable_node(name: str) -> dict: ...

  @mcp.tool()
  async def add_node(name: str, host: str, port: int, user: str, password: str, mode: str) -> dict: ...
  ```
- `run_agent.py` seeds `NodeRegistry` from existing pool connections at startup, constructs `NodeService`, passes both to `register_tools`

### Tests added

File: `tests/agent/test_mcp_node_tools.py`

| Test | What it checks |
|------|---------------|
| `test_tool_registration_includes_all_six_node_tools` | All 6 tool names present in registered tools |
| `test_get_device_info_not_registered` | `get_device_info` absent from registered tools |
| `test_get_status_response_has_status_and_nodes` | Response shape has `status` and `nodes` keys |
| `test_disable_node_keeps_node_in_status` | Disabled node still present in `get_status` result |
| `test_enable_node_returns_enabled_shape` | `{"status": "enabled", "name": ...}` |
| `test_remove_node_returns_removed_shape` | `{"status": "removed", "name": ...}` |
| `test_add_node_returns_bootstrap_not_implemented` | Status field is `bootstrap_not_implemented` |
| `test_add_node_result_has_no_password_field` | No `password` key in return value |
| `test_get_node_info_all_returns_nodes_list` | Response has `nodes` list |
| `test_get_node_info_single_returns_one_node` | `nodes` list contains exactly one entry |
| `test_get_node_info_unknown_returns_error` | Returns error shape for unknown name |

All handler tests use a mocked `NodeService`.

### Targeted pytest command

```bash
pytest tests/agent/test_mcp_node_tools.py -v
```

Full regression (phases 1–5):

```bash
pytest tests/ -v --ignore=tests/integration
```

### MCP validation step

Start gateway after pytest passes:

```bash
python3 app.py
```

Confirm endpoint at `http://localhost:8000/mcp`. Verify:
1. All 6 node tools are visible.
2. `get_device_info` is absent.
3. Invoke `get_status` and `get_node_info` (read-only smoke test) — confirm response shapes.

### Completion gate

- All `test_mcp_node_tools.py` tests pass.
- All prior phase tests still pass.
- Gateway starts without error.
- `get_status` and `get_node_info` return expected shapes via live MCP.
- `get_device_info` confirmed absent.

---

## Phase 6 — Docs + live MCP validation

### Files touched

| File | Action |
|------|--------|
| `docs/SECURITY.md` | Modify — add **Assisted Node Onboarding** section |
| `docs/MCP_VALIDATION_GUIDE.md` | Modify — smoke test updated to read-only node tools; add task-focused validation section for this slice |
| `docs/ARCHITECTURE.md` | Modify — node API surface, semantic model, and pool seam in current boundary section |

### Behavior delivered

**`docs/SECURITY.md`** — New section: **Assisted Node Onboarding**
- Documents the `add_node` credential contract.
- States: bootstrap is not yet implemented; `add_node` returns `bootstrap_not_implemented` and does not add to the registry.
- Credential handling rules: no storage, no logging, no echoing, no inclusion in responses.
- Clearly distinguishes current behavior from intended future onboarding behavior.

**`docs/MCP_VALIDATION_GUIDE.md`** — Updates:
- Standard smoke test section: `get_status` and `get_node_info` only (read-only).
- Remove `get_device_info` from any smoke test references.
- New section: **Task-focused validation — Node Management API slice**, documenting invocation of all 6 tools including mutating ones with safe synthetic test data, and the expected evidence block format.
- Explicit note explaining the smoke test vs. task validation split.

**`docs/ARCHITECTURE.md`** — Updates to current boundary section:
- Node-oriented MCP API surface (6 tools).
- `NodeRegistry` and `NodeService` as internal components.
- `ConnectionPool` seam methods (`disable_connection`, `enable_connection`, `remove_connection`).
- Semantic model: `node` / `connection` / `pool` distinction.

### Tests added

No new test files in this phase. Any gaps found during live MCP validation that require test changes are addressed in `test_node_service.py` or `test_mcp_node_tools.py`.

### Targeted pytest command

Full regression before recording evidence:

```bash
pytest tests/ -v --ignore=tests/integration
```

### MCP validation step

Start gateway:

```bash
python3 app.py
```

Endpoint: `http://localhost:8000/mcp`

**Smoke test (read-only):**
1. Invoke `get_status` — confirm `{"status": "ok", "nodes": [...]}` shape.
2. Invoke `get_node_info` with no name — confirm `{"nodes": [...]}` shape.

**Task-focused validation (this slice):**
3. Invoke `add_node` with synthetic test data (e.g., `name="test-node-01"`, `host="192.0.2.1"`, `port=22`, `user="testuser"`, `password="REDACTED"`, `mode="direct"`) — confirm `bootstrap_not_implemented` response and no password in return.
4. Invoke `disable_node` on a configured node — confirm `{"status": "disabled", ...}` and node still present in `get_status`.
5. Invoke `enable_node` on the same node — confirm `{"status": "enabled", ...}`.
6. Invoke `remove_node` on the same node — confirm `{"status": "removed", ...}` and node absent from `get_status`.

Record evidence block per the validation guide format.

### Completion gate

- All docs updated and consistent with the corrected architecture.
- Full pytest suite passes (no ignored tests except integration).
- Live MCP evidence recorded for all 6 tools.
- Smoke test confirmed read-only.
- Task-focused validation confirms all 4 mutating tools return correct shapes and state transitions.
- `get_device_info` confirmed absent throughout.
- This slice is complete.

---

## Cross-phase constraints

These rules apply to every phase:

| Constraint | Applies to |
|-----------|------------|
| `NodeRuntimeState` is never stored in `NodeRegistry` | Phases 1–6 |
| `disable_node` uses `pool.disable_connection()`, not `connection.close()` | Phase 4+ |
| `remove_node` uses `pool.remove_connection()`, not `connection.close()` | Phase 4+ |
| `add_node` never adds to registry if bootstrap cannot be validated | Phase 4+ |
| Password never logged, stored, or returned | Phase 4+ |
| All 6 MCP tools use explicit typed arguments (not `params` dict) | Phase 5+ |
| Terms `device`, `edge`, `remote`, `target` prohibited in new code | All phases |
| `get_status` derives `pool_state` from live pool query, not registry | Phase 3+ |
