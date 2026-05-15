# Roo-Assisted MCP Exploratory Validation Loop

## Slice goal

Establish a phased delivery path for a reliable Roo-assisted exploratory MCP validation loop where gateway startup and listener reliability are proven before Roo tool-surface validation begins.

## Core boundary and architectural direction

- Keep the gateway MCP-native.
- Do not build a custom REST API.
- Investigate native Python MCP/FastMCP HTTP-capable transport first.
- Prefer removing `mcpo` from the dev/runtime path if native Python MCP HTTP transport is viable.
- If native HTTP transport is not viable, document why and use the smallest working `mcpo` path.
- Do not introduce supervisors, hot reload, process managers, or broad lifecycle infrastructure in this slice.
- Manual start/restart is acceptable in this slice.

## Process definition

### When Roo may call MCP tools

- Roo may call MCP tools for exploratory/manual validation of:
  - startup readiness,
  - tool visibility,
  - request/response shape,
  - and one harmless status-style invocation.

### What exploratory MCP calls are not

- Exploratory MCP calls are not regression tests.
- Exploratory observations do not replace pytest evidence.

### Handoff to pytest

- When behavior stabilizes and expected output becomes clear, convert that expectation into pytest coverage.
- Keep conversion small and directly tied to observed stable behavior.

## Role responsibilities

### Roo Architect responsibilities

- Keep scope grounded and avoid speculative architecture.
- Keep exploratory validation and regression proof clearly separated.
- Define phase goals, transitions, and acceptance boundaries.

### Roo Orchestrator responsibilities

- Execute agreed exploratory validation steps.
- Capture observed startup logs, tool visibility, invocation outcomes, and conclusions.
- Create or update pytest coverage for stable behavior where appropriate.
- Preserve the gateway-as-SUT boundary during validations.

## Phased delivery plan

### Phase 1 — Transport viability discovery

Goal:

Determine whether the currently installed Python MCP/FastMCP package can run the gateway as a listener without relying on `mcpo`, or prove that it cannot.

Tasks:

- Inspect installed MCP/FastMCP capabilities in the devcontainer.
- Record the exact installed MCP package name and version for this validation run.
- Identify supported `FastMCP.run(...)` transports.
- Determine how host and port are configured for any HTTP-capable transport.
- Confirm whether existing tool registration can remain unchanged.
- Determine what endpoint Roo should connect to if native HTTP works.
- Explicitly distinguish MCP protocol endpoint shape from any plain REST or health endpoint shape.
- Record findings in this plan before implementation.

Exit criteria:

- Native Python MCP HTTP-capable transport viability is known.
- Exact startup command shape is known.
- Whether `mcpo` can be removed from the dev path is known.
- No product behavior changed yet, except exploratory local checks if needed.

Transition rule to Phase 2:

- Go only when one concrete startup path is selected and written in this plan.

Phase 1 findings recorded:

- Runtime package validated in devcontainer: `mcp==1.27.1`.
- `FastMCP.run(...)` signature observed:
  - `(self, transport: Literal['stdio', 'sse', 'streamable-http'] = 'stdio', mount_path: str | None = None) -> None`
- Transport viability result:
  - Native HTTP-capable transport is viable via `transport='streamable-http'`.
  - `transport='sse'` is also network-capable but distinct from streamable HTTP.
- Endpoint shape distinction:
  - MCP endpoint should be treated as protocol transport endpoint for MCP messages.
  - It is not a custom REST API surface and should not be treated as one.
  - Any plain HTTP health response, if present, is incidental and not the product API contract.
- Tool registration impact:
  - Existing `FastMCP` tool registration model can remain unchanged for transport switch exploration.
- Startup command shape direction now known for Phase 2 exploration:
  - Python process path can target `FastMCP.run(transport='streamable-http', mount_path=...)` wiring.
  - Host and port configuration details still need concrete code-path confirmation during Phase 2 implementation.
- `mcpo` removal decision status:
  - Candidate for removal from dev startup path is plausible based on available native transports.
  - Final remove/retain decision is deferred until Phase 2 startup proof is completed and reviewed.

Phase 2 pre-implementation SDK findings:

- `FastMCP.run(transport='streamable-http')` dispatches to `run_streamable_http_async`.
- `run_streamable_http_async` creates a Uvicorn server from `self.streamable_http_app()`.
- Host and port are taken from `self.settings.host` and `self.settings.port`.
- Log level is taken from `self.settings.log_level`.
- `mount_path` is not used for `streamable-http` in `FastMCP.run(...)` and is only threaded for `sse`.
- Endpoint readiness checks in Phase 2 should target the MCP streamable HTTP endpoint surface, not a custom REST contract.

### Phase 2 — Minimal startup implementation

Goal:

Make `scripts/start-agent.sh` start one reliable gateway listener using the chosen transport.

Tasks:

- If native Python MCP HTTP transport is viable, update the Python startup path to use it.
- Make transport, host, port, and connection config configurable with simple defaults.
- Update `scripts/start-agent.sh` so it starts the Python process directly if `mcpo` is no longer needed.
- If `mcpo` remains necessary, keep it and avoid extra lifecycle infrastructure.
- Fix only startup blockers required for the listener to run.
- Do not add unrelated gateway features.

Exit criteria:

- `bash scripts/start-agent.sh` starts successfully in the devcontainer.
- A real listener exists on the expected port.
- Stopping the terminal process is understandable and manually recoverable.
- No orphan/lifecycle-hardening work is introduced unless absolutely required for manual operation.

Transition rule to Phase 3A:

- Go only when listener readiness is reproducible across at least one stop/start cycle.

### Phase 3A — Roo MCP client validation procedure

Goal:

Teach Roo to validate the streamable-http MCP endpoint correctly, including session establishment, tool discovery, and tool invocation.

Tasks:

- Determine the correct Roo MCP configuration for FastMCP streamable-http.
- Confirm endpoint target between `http://localhost:8000` and `http://localhost:8000/mcp`.
- Confirm whether an initialize/session step is required before tool calls.
- Capture the exact Roo-side configuration that works.
- Capture and document sequence: connect endpoint -> establish session -> enumerate tools -> invoke `get_status` -> inspect gateway logs.
- Record common failure modes, including `Session not found`, as setup/protocol errors rather than gateway tool failures.

Exit criteria:

- A documented repeatable Roo MCP client validation procedure exists.
- Transport/session failures are clearly distinguished from gateway tool failures.
- `get_status` succeeds once using the documented procedure.

Transition rule to Phase 3B:

- Go only when the Roo-side streamable-http client/session procedure is validated and documented.

### Phase 3B — Roo connection smoke validation

Goal:

Verify Roo can see the gateway as the system under test.

Tasks:

- Configure Roo to connect to the chosen endpoint.
- Verify Roo can enumerate the exposed MCP tools.
- Verify Roo can invoke one read-only/status-style tool.
- If no harmless status/listing tool exists, record that as a tool-surface gap rather than inventing a test-only tool.
- Capture startup logs, tool list visibility, invocation result, and conclusion.

Exit criteria:

- Roo can connect to the gateway endpoint.
- Roo can see the MCP tool surface.
- Roo can perform one harmless invocation, or the missing harmless tool is explicitly recorded as a gap.
- The observation capture protocol has been exercised once.

Transition rule to Phase 4:

- Go only when Phase 3A is complete and exploratory observations from Phase 3B are stable enough to convert at least one startup/config expectation into pytest scope.

### Phase 4 — Regression coverage and documentation

Goal:

Turn stable findings into tests and document the process boundary.

Tasks:

- Add or update pytest coverage for fixed startup/config behavior where appropriate.
- Update `docs/DEVELOPER.md` with one concise section describing:
  - manual start command,
  - Roo exploratory MCP validation purpose and limits,
  - Architect responsibilities,
  - Orchestrator responsibilities,
  - exploratory MCP calls are not regression tests,
  - stable observations should become pytest coverage.
- Keep documentation centralized. Do not spread this process across many files.
- Update this plan status/checklist with actual findings.

Exit criteria:

- Relevant pytest tests pass.
- `docs/DEVELOPER.md` contains the process boundary.
- This plan records what was validated and what remains open.
- The slice clearly separates exploratory MCP validation from pytest regression testing.

## Observation capture protocol

For each exploratory run, capture:

- startup command used,
- startup logs,
- listener availability at the chosen endpoint and port,
- exposed tool list visible to Roo,
- one harmless/status-style invocation result,
- and pass/fail conclusion against acceptance criteria.

## Validation Case 1 context

Current startup instability observed in this slice:

- `mcpo` process can terminate while `python3 /app/app.py` continues.
- Forwarded port visibility can diverge from actual listener state.

Diagnostic focus in this plan:

- Treat transport startup and listener reliability as prerequisite work before Roo exploratory MCP validation.

## Documentation and rules update scope

Single canonical process update for this slice:

- `docs/DEVELOPER.md` only.

## Acceptance criteria for this slice

This slice is complete when all are true:

- The gateway starts and listens through the chosen transport.
- Roo connects to the gateway as the system under test.
- Roo can inspect the tool surface.
- Roo can make one harmless/read-only validation call or record a tool-surface gap.
- Logs are sufficient to understand startup and the validation call.
- Stable startup/config behavior is covered by pytest where appropriate.
- The process boundary is documented in `docs/DEVELOPER.md`.

## Working slice status checklist

- [x] Phase 1 completed with recorded transport viability findings.
- [x] Phase 2 completed with reliable manual startup path.
- [ ] Phase 3A completed with documented Roo MCP client validation procedure.
- [ ] Phase 3B completed with Roo smoke validation evidence.
- [ ] Phase 4 completed with pytest and documentation updates.

## Orchestrator delivery plan

This section preserves the current plan as the active working slice and breaks execution into reviewable steps with stop/go checks.

### Delivery Step 1 — Execute Phase 1 transport viability discovery

Scope:

- Inspect installed MCP/FastMCP runtime behavior.
- Record exact installed MCP package name and version.
- Confirm supported `FastMCP.run(...)` transport values.
- Determine host and port configuration shape for HTTP-capable transport.
- Capture exact endpoint Roo should target if native HTTP is viable.
- Distinguish MCP endpoint shape from plain REST or health endpoint shape.

Expected file changes in this step:

- `plans/roo-assisted-mcp-validation-loop.md` only for recorded findings.

Validation commands:

```bash
python3 -c "import importlib.metadata as m; print('mcp', m.version('mcp'))"
python3 -c "import mcp,inspect; from mcp.server.fastmcp import FastMCP; print(mcp.__file__); print(inspect.signature(FastMCP.run))"
python3 -c "from mcp.server.fastmcp import FastMCP; print([a for a in dir(FastMCP) if 'run' in a.lower() or 'transport' in a.lower()])"
```

Stop/Go criteria:

- Go when one concrete startup path is chosen and documented.
- Stop if transport behavior is ambiguous and requires unresolved assumptions.

### Delivery Step 2 — Execute Phase 2 minimal startup implementation

Scope:

- Implement only the startup path required for a reliable listener.
- Keep startup parameters simple and configurable.
- Use direct Python startup with MCP-native transport (no `mcpo` wrapper).

Expected file changes in this step:

- `entrypoint.sh` to execute `python3 /app/app.py` directly with env-defaulted args
- `Dockerfile` env naming aligned to `MCP_PORT`
- `pyproject.toml` dependency cleanup if `mcpo` is no longer required

Validation commands:

```bash
python3 app.py --transport streamable-http --host 0.0.0.0 --port 8000 --connection-config ''
ss -ltnp | grep ':8000'
```

Validation note:

- Listener check is first-pass only.
- Add an endpoint-aware MCP readiness check after the concrete `streamable-http` mount path and endpoint shape are confirmed in implementation.

Stop/Go criteria:

- Go when startup succeeds and listener is present on expected port after one restart cycle.
- Stop if fixes expand into broad lifecycle infrastructure or unrelated gateway features.

Phase 2 execution notes (actual run):

- Canonical startup path was simplified to direct Python execution:
  - `python3 app.py`
  - with defaults in `app.py`: `transport=streamable-http`, `host=0.0.0.0`, `port=8000`, `connection_config=""`.
- `scripts/start-agent.sh` was removed from the active validation path to avoid legacy defaults and indirection.
- Container startup path aligned to direct Python execution in `entrypoint.sh` with env defaults:
  - `MCP_TRANSPORT` default `streamable-http`
  - `MCP_HOST` default `0.0.0.0`
  - `MCP_PORT` default `8000`
  - `CONNECTION_CONFIG` default `/data/config/connections.json`
- `Dockerfile` now uses `MCP_PORT` (`ENV` + `EXPOSE`) for naming consistency.
- `mcpo` removed from runtime dependencies in `pyproject.toml` because startup path no longer uses it.
- Direct Python validation previously confirmed listener readiness when run with explicit equivalent arguments:
  - `python3 app.py --transport streamable-http --host 0.0.0.0 --port 8000 --connection-config ''`
  - broad and narrowed socket checks showed `python3` listening on `0.0.0.0:8000`.
- Logs/observations:
  - Agent process can log recurring connection-pool reconnect noise (`Error reading SSH protocol banner`) while the MCP listener is healthy.
  - Listener readiness and connection-pool health are treated as separate concerns for this phase gate.
- Phase gate status:
  - Startup path simplification is implemented.
  - Final stop/start cycle for no-arg `python3 app.py` completed via bounded probe (`timeout 12s python3 app.py`) to avoid cross-terminal process interference.
  - Listener proof captured during probe:
    - `LISTEN ... 0.0.0.0:8000 ... users:(("python3",pid=...,fd=...))`
  - Startup/runtime proof captured during probe:
    - `Agent registered all handlers. MCP loop initiated (transport=streamable-http, host=0.0.0.0, port=8000).`
    - `FastMCP effective settings before run (transport=streamable-http, settings.host=0.0.0.0, settings.port=8000, ...)`
    - `Uvicorn running on http://0.0.0.0:8000`
  - Controlled shutdown observed after timeout, confirming one full start/stop validation cycle.
  - Phase 2 gate result: **PASS** (do not begin Phase 3 until explicitly directed).

### Delivery Step 3 — Execute Phase 3B Roo connection smoke validation

Scope:

- Point Roo to chosen MCP endpoint (`http://localhost:8000`).
- Confirm tool enumeration.
- Invoke one harmless status/read-only style tool, or record explicit gap.

Expected file changes in this step:

- `plans/roo-assisted-mcp-validation-loop.md` for captured observations and conclusions.

Validation actions:

- Roo endpoint connection attempt (`http://localhost:8000`).
- Roo tool-list observation capture.
- One harmless invocation capture, or tool-surface gap capture.

Stop/Go criteria:

- Go when connection and tool-surface evidence are captured once.
- Stop if endpoint is reachable but MCP tool surfacing is not reproducible.

Observed evidence (2026-05-15 UTC):

- Endpoint target requested for this step: `http://localhost:8000`.
- Endpoint actually configured in Roo MCP config (`.roo/mcp.json`): `http://localhost:8000/mcp` with `type: streamable-http`.
- Roo-facing tool surface observed from config (`alwaysAllow`): `get_device_info`, `get_status`.
- Harmless/read-only invocation attempted: `get_status`.
- Invocation result:
  - HTTP POST failure returned `404`.
  - JSON-RPC error payload: `{"jsonrpc":"2.0","id":"server-error","error":{"code":-32600,"message":"Session not found"}}`.
  - Roo extension stack reported MCP call failure during POST with `McpError: MCP error -32600: Session not found`.
- Runtime logs visible during the same validation window:
  - Repeated `Still waiting for tunnel inbound...`.
  - Reconnect churn including `Connection inbound is down. Attempting to reconnect...` and outbound failures `Error reading SSH protocol banner`.

Phase 3B exit-criteria conclusion:

- **STOP (not GO)** for Delivery Step 3 completion gate.
- Reason: connection attempt evidence and invocation evidence were captured once, but MCP tool-call execution was not reproducibly successful due to session-level failure (`Session not found`), satisfying the step's stop condition: endpoint reachable path configured yet tool surfacing/call behavior not reproducible.
- Classification note: prior `Session not found` evidence indicates a missing or incorrect client protocol/session procedure in Roo setup, not a gateway tool failure.

### Delivery Step 4 — Execute Phase 4 regression and documentation updates

Scope:

- Convert stable startup/config findings into focused pytest coverage.
- Add one concise process section in `docs/DEVELOPER.md`.

Expected file changes in this step:

- `tests/integration/test_app_stdio.py` and or other focused startup tests where appropriate
- `docs/DEVELOPER.md`
- `plans/roo-assisted-mcp-validation-loop.md` status updates

Validation commands:

```bash
pytest tests/integration/test_app_stdio.py
pytest
```

Stop/Go criteria:

- Go to completion when targeted tests pass and docs capture the process boundary.
- Stop if proposed test coverage cannot be tied to stable observed behavior.

### Delivery constraints for Orchestrator execution

- Avoid speculative cleanup.
- Avoid supervisors, hot reload, or process-manager infrastructure in this slice.
- Keep each step reviewable before moving to the next phase.
