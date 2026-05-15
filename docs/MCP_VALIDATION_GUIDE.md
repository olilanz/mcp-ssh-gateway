# MCP Validation Guide

## Purpose

MCP validation is the live product-surface validation loop for `mcp-ssh-gateway`.

The loop complements, but does not replace, pytest.

The goal is:

- use TDD where suitable for algorithmic core components,
- implement iteratively until tests pass,
- then validate MCP-exposed behavior through the running agent,
- collect evidence,
- decide whether the evidence suggests more implementation, new tests, or documentation updates,
- include the evidence in the task status report.

## Validation model

### 1. Static review

- Read code, docs, plans, and tests.
- Verify intended design and boundaries.

### 2. Automated regression

- Use pytest.
- Best for deterministic logic, config parsing, connection object behavior, result shaping, and edge cases.
- Use TDD for algorithmic core components or where practical.

### 3. Live MCP validation

- Use the running gateway as the system under test.
- Validate exposed MCP behavior, tool visibility, tool descriptions, request/response shape, logs, and operational behavior.

### 4. Evidence review

- Decide whether observed behavior is acceptable.
- Decide whether pytest coverage should be added or hardened.
- Decide whether docs/rules need updates.
- Record findings in the task report.

## Standard smoke test

A minimal repeatable smoke test to run after every gateway change:

1. Start gateway:

   ```bash
   python3 app.py
   ```

2. Confirm endpoint:

   ```
   http://localhost:8000/mcp
   ```

3. Confirm stateless streamable-http is in use (`stateless_http=True`, `json_response=True` in [`agent/run_agent.py`](../agent/run_agent.py)).

4. Confirm Roo can see tools.

5. Invoke:
   - `get_status`
   - `get_device_info`

6. Capture:
   - startup command
   - endpoint
   - tools observed
   - call inputs
   - outputs
   - relevant logs
   - pass/fail conclusion

## Task-focused exploratory validation

After the smoke test, focus exploratory MCP validation on the areas affected by the current task and latest changes.

Examples:

- **Tool registration changed**: enumerate tools and verify names/descriptions.
- **Input/output shape changed**: invoke affected tools with representative inputs and inspect response shape.
- **Connection/pool behavior changed**: validate exposed connection/pool state and logs.
- **Command execution changed**: validate command execution behavior against a safe target or controlled fixture.
- **Startup/transport changed**: validate listener readiness, endpoint behavior, and restart behavior.
- **Logging/observability changed**: validate that logs explain the operation and failure mode.

## Iterative development loop

1. Identify expected behavior.
2. Add or update pytest first where practical.
3. Implement or change code.
4. Run targeted tests.
5. Run full or relevant pytest.
6. Start or restart gateway.
7. Run MCP smoke test.
8. Run task-focused exploratory validation.
9. Review evidence.
10. Decide:
    - implementation complete,
    - more code needed,
    - pytest needs hardening,
    - docs/rules need updates,
    - or architecture needs review.
11. Record evidence in the task status report.

## Lifecycle ownership

Roo may start the gateway as a task-scoped validation process when needed.

Rules:

- Prefer reusing a known-good running gateway if one exists and matches current code.
- If Roo starts the gateway, it must track the process it started (record PID).
- Roo must stop only the process it started after validation. Do not kill pre-existing gateway processes unless they block the required port.
- If port 8000 is occupied by a pre-existing process, kill it before starting a task-scoped process. Record both the pre-existing PID and the task-scoped PID.
- Roo must not introduce supervisors, watchers, hot reload, or persistent lifecycle infrastructure unless explicitly requested.
- After validation, Roo must confirm: process dead AND port released.

Canonical startup command:

```bash
python3 app.py
```

Canonical endpoint:

```
http://localhost:8000/mcp
```

Current supported network transport: stateless streamable-http (`stateless_http=True`, `json_response=True`).

SSE and stateful sessions are out of scope unless explicitly requested in a future slice.

## Use during planning and investigation

Some Roo modes may use the MCP agent before implementation:

- **Architect mode** may call MCP tools during analysis to complement static code and documentation review.
- **Ask mode** may call MCP tools to inspect live behavior when answering design or debugging questions.
- **Orchestrator/Debug mode** may call MCP tools to validate implementation slices.

Boundary:

- Calls during planning/investigation are exploratory evidence.
- They must not be confused with regression tests.
- They should be limited to safe/read-only calls unless mutation is explicitly part of the task.
- The gateway remains the system under test, not a general-purpose automation substrate.

## Evidence requirements

For every live MCP validation, Roo must record:

- why validation was needed,
- gateway startup method (command used, PID recorded),
- endpoint,
- tools observed,
- tool calls performed,
- input values,
- observed outputs,
- relevant logs,
- pass/fail conclusion,
- whether pytest coverage was added, updated, or intentionally deferred (with reason),
- whether docs/rules need updates.

## Completion gate

A task that changes MCP-exposed behavior is not complete until:

- relevant pytest has passed, or pytest deferral is explicitly justified,
- live MCP validation evidence has been captured,
- evidence has been reviewed,
- any required follow-up tests/docs/rules are identified,
- and the status report includes the validation result.

### Gate applies when a task changes

- MCP tool registration,
- tool names or descriptions,
- tool input/output shape,
- connection or pool behavior exposed through tools,
- command execution behavior,
- startup or transport behavior,
- logging or observability used to interpret tool calls.

### Gate does not apply to

- pure documentation-only changes unrelated to MCP behavior,
- internal refactors with no MCP-visible behavior change,
- tests-only changes unless they alter expected MCP-visible behavior.

## Status report template

Include the following block in every task report where the gate applies:

```
MCP validation:
- Gate applicable: yes/no
- Reason: <why gate applies or does not apply>
- Gateway startup: <command used, PID>
- Endpoint: http://localhost:8000/mcp
- Tools observed: <list>
- Calls performed: <tool names and inputs>
- Results: <outputs>
- Logs reviewed: <relevant log lines>
- Conclusion: PASS / FAIL / NOT APPLICABLE
- Pytest follow-up: added / deferred (<reason>) / not needed
- Docs/rules follow-up: <any needed update or "none">
```
