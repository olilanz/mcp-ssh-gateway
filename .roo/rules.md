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

## Documentation Governance

- Treat [`docs/DOCUMENTATION_GUIDE.md`](../docs/DOCUMENTATION_GUIDE.md) as the authoritative standard for documentation style, placement, and governance.
- Documentation must be updated before completing tasks that change behavior, boundaries, commands, or decisions.
- Surface documentation conflicts or inaccuracies explicitly in task summaries so the team can decide whether to update docs or change implementation plans.
- When architectural boundaries change, update [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md), [`docs/TESTING_STRATEGY.md`](../docs/TESTING_STRATEGY.md), and [`docs/ARCHITECTURAL_DECISIONS.md`](../docs/ARCHITECTURAL_DECISIONS.md) in the same slice when applicable.

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
