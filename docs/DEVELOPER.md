# Developer Guide

This guide describes how to work in the repo today.

## Development Environment

- Python 3.10+ on Linux/macOS.
- `sshd`, `ssh`, and `ssh-keygen` available for integration-style tests.
- Dev Container usage is supported via [`/.devcontainer`](.devcontainer).

## Install Dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -e .
python -m pip install pytest
```

## Build/Test Commands

- Run all tests:

```bash
pytest
```

- Run connection-pool tests only:

```bash
pytest tests/agent/connectionpool
```

- Run a targeted test:

```bash
pytest tests/agent/connectionpool/test_connection.py -k constructor
```

## Lint / Type Checks

No dedicated lint/type configuration (for example Ruff/Mypy) is currently defined in [`pyproject.toml`](pyproject.toml).

## Current Test Strategy

- Unit-level behavior around [`Connection`](agent/connectionpool/connection.py), config parsing, and pool orchestration.
- Integration-style SSH tests rely on temporary local `sshd` fixtures.
- Prefer generated temporary SSH keys in tests.

`/data/keys` may exist in container/dev setups for manual runs, but tests should prefer temporary generated keys unless a test explicitly requires mounted keys.

## Current Implementation Boundary

- Direct SSH behavior is implemented via [`DirectConnection.open()`](agent/connectionpool/connection.py:145).
- Tunnel probing exists in [`TunnelConnection.open()`](agent/connectionpool/connection.py:176) and [`TunnelConnection._start_probe_timer()`](agent/connectionpool/connection.py:183).
- `TunnelConnection` can probe and connect through an already exposed local tunnel port. The agent-side SSH server that accepts reverse tunnels is not implemented in the current code.

## Contribution Notes

- Keep changes small and reviewable.
- Preserve the `Connection` facade as the public test/use boundary.
- Update docs when implementation boundaries change.
