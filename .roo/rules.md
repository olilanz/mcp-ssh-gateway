# Roo Repository Rules

## Change Scope

- Keep changes small, focused, and reviewable.
- Prefer clarity over abstraction.
- Do not introduce new framework or infrastructure unless explicitly requested.

## Architecture and Boundaries

- Do not invent architecture beyond current code and documented direction.
- Preserve the [`Connection`](agent/connectionpool/connection.py) facade as the public test/use boundary.
- Do not implement the reverse tunnel listener/server unless the slice explicitly asks for it.
- When touching docs, always distinguish implemented behavior, intended architecture, and planned work.
- Before changing architecture, update docs to explain the new boundary.
- Do not reference files that do not exist.

## Testing and SSH Keys

- Prefer generated temporary SSH keys in tests.
- Do not rely on committed or mounted keys unless a specific test explicitly requires mounted keys.

## Build and Test Commands

Install dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -e .
python -m pip install pytest
```

Run all tests:

```bash
pytest
```

Run targeted tests:

```bash
pytest tests/agent/connectionpool
pytest tests/agent/connectionpool/test_connection.py -k constructor
```
