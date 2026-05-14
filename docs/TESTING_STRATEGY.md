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
