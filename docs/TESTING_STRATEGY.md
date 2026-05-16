# Testing Strategy

## Purpose

Define what tests in this repository are expected to prove, and what they must not assume.

## Scope

- Tests must verify current implemented behavior.
- Tests must enforce architecture boundaries in [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Current Test Model

- Unit/integration tests cover connection behavior around the [`Connection`](../agent/connectionpool/connection.py) facade.
- Direct SSH behavior is tested against local `sshd` fixtures.
- Tunnel behavior testing is limited to probing/connecting through already exposed local tunnel ports.

## Non-Goals for Current Test Suite

- Tests must not assume an agent-side reverse tunnel SSH listener exists.
- Tests must not claim end-to-end reverse tunnel listener behavior.

## Operational Notes

- Prefer generated temporary SSH keys.
- Mounted keys (for example `/data/keys`) may exist in dev/container environments but are not the default for tests.

## Enforcement

- If architecture boundaries change, tests must be updated in the same slice.
- If tests rely on behavior not implemented in code, either tests or docs must be corrected before merge.

## Functional SSH Tests

Functional tests verify the gateway against a real local sshd process running inside
the devcontainer. They are marked `@pytest.mark.functional` and
`@pytest.mark.requires_sshd`.

The `spawn_sshd` fixture (defined in `tests/sshd_fixture.py`, exported via
`tests/conftest.py`) starts an isolated sshd instance with:
- A generated temporary host key and client keypair
- An absolute `AuthorizedKeysFile` path
- A random high port on `127.0.0.1`
- No interaction with the production sshd or `/etc/ssh/sshd_config`

**Run functional tests:**
```bash
pytest -m functional -v
```

**Run unit tests only (fast, no sshd):**
```bash
pytest -m "not functional"
```

Functional test files live in `tests/functional/`. Unit tests run without the
`functional` mark and do not require a running sshd process.

## Test Layer Contract

### Layer Definitions

**Unit tests (default)**
- No real sshd, no app process, no network except mocks
- Fast and deterministic — must run in < 5 seconds total
- Run with: `pytest -m "not functional and not integration" -q`
- These are the default: every PR must keep them green

**Functional tests**
- Require a live local sshd fixture (`spawn_sshd`)
- Must be marked `@pytest.mark.functional` and `@pytest.mark.requires_sshd`
- Must clean up remote files in `finally` blocks
- Must use `shlex.quote()` for any shell path interpolation
- Run with: `pytest -m functional -q`

**Integration tests**
- May start `app.py`, MCP server, or other real processes
- Must be marked `@pytest.mark.integration`
- Must have explicit process timeout and cleanup
- Must not use raw stdin/stdout JSON protocol — use actual MCP client behavior
- Run with: `pytest -m integration -q`

### Warning Policy

Warnings are treated as errors. A clean test run must have zero warnings. New warnings must either be fixed at the source or explicitly justified with a narrow filter added to the `filterwarnings` list in `pyproject.toml`. Broad warning suppression is not permitted.

### Wait Helper Contract

`_wait_for_open()` helpers in functional tests must assert clearly on timeout:
```python
assert final_state == "open", f"Expected 'open' within {timeout}s, got '{final_state}'"
```
Silent returns after timeout hide test infrastructure failures.

### Marker Commands

```bash
# Default (fast, no real SSH or processes):
pytest -m "not functional and not integration" -q

# Full functional suite (requires sshd):
pytest -m functional -q

# Integration tests (requires running app):
pytest -m integration -q

# Everything except integration:
pytest -m "not integration" -q
```
