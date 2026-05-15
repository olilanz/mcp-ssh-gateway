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

Transition rule to Phase 3:

- Go only when listener readiness is reproducible across at least one stop/start cycle.

### Phase 3 — Roo connection smoke validation

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

- Go only when exploratory observations are stable enough to convert at least one startup/config expectation into pytest scope.

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
- [ ] Phase 2 completed with reliable manual startup path.
- [ ] Phase 3 completed with Roo smoke validation evidence.
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
- Prefer native Python MCP HTTP path if viable; otherwise retain minimal `mcpo` path.

Expected file changes in this step:

- `scripts/start-agent.sh`
- `app.py` and or `agent/run_agent.py` only if required for chosen transport wiring
- no documentation edits in this step unless strictly required to run the command path

Validation commands:

```bash
bash scripts/start-agent.sh
ss -ltnp | grep ':8000'
```

Validation note:

- Listener check is first-pass only.
- Add an endpoint-aware MCP readiness check after the concrete `streamable-http` mount path and endpoint shape are confirmed in implementation.

Stop/Go criteria:

- Go when startup succeeds and listener is present on expected port after one restart cycle.
- Stop if fixes expand into broad lifecycle infrastructure or unrelated gateway features.

Phase 2 execution notes (actual run):

- Actual startup command shape now used by [`scripts/start-agent.sh`](scripts/start-agent.sh):
  - `python3 app.py --transport streamable-http --host 0.0.0.0 --port 8000 --connection-config <value>`
  - Default `<value>` in script is `/data/config/connections.json`; an additional run used `CONNECTION_CONFIG=''`.
- Validation commands executed:
  - `bash scripts/start-agent.sh`
  - `ss -ltnp | grep ':8000'`
  - stop/start cycle repeated, then `ss -ltnp | grep ':8000'` again.
- Logs/observations:
  - Agent process stays up and repeatedly logs connection-pool reconnect attempts.
  - Observed recurring SSH-side errors from existing connection targets (`Invalid key` and `Error reading SSH protocol banner`).
  - No startup evidence of a bound MCP listener on port 8000 in this run.
- Listener check results:
  - First cycle: `ss -ltnp | grep ':8000'` returned no match.
  - Second cycle (after stop/start): `ss -ltnp | grep ':8000'` returned no match.
- Unresolved blocker:
  - Expected streamable HTTP listener was not observed on `:8000` despite process running; startup path wiring is implemented but listener readiness is not yet proven in this environment.
- Endpoint shape note:
  - Endpoint shape is explicitly treated as observed/not-assumed; this step did not infer any `mount_path` route and did not assume endpoint URL shape from configuration alone.

### Delivery Step 3 — Execute Phase 3 Roo connection smoke validation

Scope:

- Point Roo to chosen endpoint.
- Confirm tool enumeration.
- Invoke one harmless status/read-only style tool, or record explicit gap.

Expected file changes in this step:

- `plans/roo-assisted-mcp-validation-loop.md` for captured observations and conclusions.

Validation actions:

- Roo endpoint connection attempt.
- Roo tool-list observation capture.
- One harmless invocation capture, or tool-surface gap capture.

Stop/Go criteria:

- Go when connection and tool-surface evidence are captured once.
- Stop if endpoint is reachable but MCP tool surfacing is not reproducible.

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
