# Documentation Update Plan

## Purpose

This plan asks Roo to help build out the documentation for `mcp-ssh-gateway` from the current codebase and the project understanding captured below.

The current documentation has been realigned to a better framing, but it should now be reviewed and improved by grounding it carefully in the repository.

Roo must not treat the current docs as automatically complete or correct. Roo should inspect the code, compare it with the stated project direction, and help shape durable documentation that explains the agent clearly.

---

## First Principle

Ground yourself in the code before editing documentation.

Before changing docs, inspect:

- `app.py`
- `agent/run_agent.py`
- `agent/mcp_handlers.py`
- `agent/connectionpool/`
- `agent/connection_result.py`
- `scripts/`
- `pyproject.toml`
- `Dockerfile`
- `.roo/rules.md`
- existing files in `docs/`

Identify what is implemented, what is partially implemented, and what is intended but not implemented yet.

Documentation must not claim behavior that does not exist in code.

At the same time, documentation should not reduce the project to its current incomplete implementation. It should explain the intended system shape, while clearly separating current state from direction.

---

## Complete Project Understanding

`mcp-ssh-gateway` is an MCP-native boundary agent for remote operational capability.

It gives LLMs and automation systems controlled arms and legs into selected remote machines through SSH-based connections. The goal is to bring shell capability to the user's fingertips without requiring the user to remember every command, flag, diagnostic step, or multi-system workflow.

The LLM provides reasoning, planning, interpretation, and workflow composition. The gateway provides operational reach into real systems.

SSH is the transport, not the whole product.

The product is the boundary between an orchestrator and selected real-world environments.

---

## The Core Promise

When successful, the gateway allows an LLM to:

- inspect configured remote environments,
- discover what tools, hardware, and network access they provide,
- choose which machine is best suited for a task,
- execute commands or scripts through selected connections,
- transfer artifacts where needed,
- coordinate work across multiple machines,
- and explain results back to the user in a useful form.

The user no longer has to manually remember and type every shell command. The LLM can plan bigger steps, generate scripts, run them through the gateway, interpret results, and present well-structured feedback.

The primary areas of work include, but are not limited to:

- systems automation,
- remote administration,
- diagnostics and troubleshooting,
- penetration testing,
- offensive security research,
- distributed operational workflows,
- infrastructure inspection,
- and AI-assisted task execution.

---

## Boundary Agent Model

The gateway is the trust and execution boundary.

Systems such as Open WebUI, n8n, OpenClaw, or other MCP-compatible orchestrators should not manage:

- SSH passwords,
- private keys,
- target hostnames,
- network topology,
- reverse tunnel mechanics,
- or connection secrets.

They use the gateway as the boundary.

The orchestrator gets capability, not custody.

This phrase is important. It means the orchestrator can request work through MCP tools, but the gateway owns the credentials, connection mechanics, discovery, cache, and execution records.

---

## Connection as an Arm

A connection is a trusted operational arm into a remote machine.

It is not merely an SSH target.

A connection represents a remote capability environment where commands can be executed and where useful resources may exist.

A connected machine may provide:

- shell access,
- local command-line tools,
- specialized hardware,
- GPU acceleration,
- databases,
- storage,
- network locality,
- attached devices,
- interpreter environments,
- build tools,
- security tools,
- or access into isolated infrastructure.

The agent itself is not intended to run on the edge. The agent should be protected. The edge is remote: it is where the LLM reaches through the gateway.

---

## Capability Discovery and Cache

The gateway should discover what each connection can do.

Discovery should start small and general, then grow toward more purposeful discovery.

Baseline discovery should include information such as:

- operating system,
- architecture,
- hostname,
- user context,
- network configuration,
- internet access,
- memory,
- disks,
- GPU availability,
- installed interpreters,
- local toolchains,
- installed tools,
- and other relevant environment capabilities.

Discovered capabilities should be normalized and stored in a file per connection.

The LLM should be able to query those capabilities through MCP tools.

The sum of discovered capability information lets the LLM plan efficient execution of the task at hand. It can decide which connection should be used for which task, and it can use multiple machines collaboratively for complex workflows.

The capability cache is not just operational inventory. It is part of the LLM's planning surface.

---

## Runbooks and Skills

The gateway becomes more powerful when paired with runbooks, skills, and procedures.

The LLM is the brain. Runbooks and skills provide procedural memory. The gateway provides the arms and legs.

Together, they allow automation systems to perform larger workflows through real machines while keeping actions visible and attributable.

Documentation should explain this carefully. Do not make it sound magical. The correct framing is practical: runbooks give reusable procedure, the LLM plans and adapts, and the gateway executes through selected remote environments.

---

## Agency and Auditability

For now, the intended usage is in test and controlled environments where the LLM may have broad agency.

The safety model is not primarily about preventing the LLM from doing anything useful. The safety model is about:

- limiting the reachable world to configured connections,
- keeping credentials inside the gateway,
- using explicit SSH trust,
- avoiding long-term password storage,
- logging executed actions,
- and supporting post-mortem review.

The gateway should keep a record of what was executed so that behavior can be inspected later.

This is especially important because the project intentionally supports powerful workflows, including systems automation and offensive security testing in controlled environments.

---

## Onboarding and Trust Establishment

Target onboarding may be a valid future workflow.

The gateway may help establish or register a new connection, especially by using standard SSH identity practices and the `.ssh` folder.

The preferred direction is passwordless connectivity. If passwords are used during onboarding, the system should try to establish key-based access so passwords are not stored long-term.

New targets should not become part of the reachable operational world implicitly. They must become explicit registered connections.

Documentation should avoid saying onboarding is categorically out of scope.

---

## Connection Modes

The project has two reachability modes.

### Direct Mode

Direct mode is used when the gateway can reach the remote machine directly.

The gateway opens outbound SSH to the target.

Direct mode is useful in trusted infrastructure where the edge machine is known and reachable, such as internal networks, VPN-connected environments, static labs, or development setups.

### Reverse Tunnel Mode

The correct human-facing term is reverse tunnel mode.

The current config value may still be `mode: "tunnel"`, but documentation should explain the operational model as reverse tunnel mode.

Reverse tunnel mode is used when the remote machine is not reachable from the gateway, but the remote machine can reach the gateway.

The edge initiates connectivity, exposes its own SSH service through a reverse tunnel, and the gateway connects back through the exposed local tunnel port.

This is useful for locked-down infrastructure, NATed networks, outbound-only environments, headless devices, mobile environments, and remote labs.

Headless devices should generally prefer reverse tunnel mode.

---

## Current Implementation Boundary

Roo must inspect code and verify this, but the current known boundary is:

Implemented or partially present:

- MCP startup using FastMCP over STDIO,
- static connection configuration,
- connection pool scaffolding,
- `Connection` facade,
- direct SSH using Paramiko,
- reverse tunnel probing through an already exposed local port,
- structured command result model,
- scripts for environment discovery or fast inspection,
- early capability/cache concepts.

Not fully implemented:

- full agent-side reverse tunnel SSH listener lifecycle,
- complete end-to-end reverse tunnel establishment,
- mature capability discovery and normalized cache,
- rich task routing,
- full file transfer workflow,
- full script execution workflow,
- complete onboarding workflow.

Documentation must separate these categories clearly.

Do not claim that reverse tunnel listener behavior exists until code implements it.

---

## Documentation Goals

The docs should help a reader understand:

- what the project is,
- why it exists,
- how it is different from a generic SSH gateway,
- how MCP fits,
- why the gateway owns credentials and connection mechanics,
- how connections represent remote capability environments,
- how capability discovery and cache support planning,
- how direct and reverse tunnel modes differ,
- where current implementation ends,
- and how the project can grow without losing simplicity.

The tone should be direct, grounded, and useful.

Avoid marketing language.

Avoid speculative promises.

Explain the fascination and usefulness, but keep it concrete.

---

## Documentation Placement

Follow `docs/DOCUMENTATION_GUIDE.md`.

Use this placement model:

- `README.md`: repo entry point, purpose, install/test basics, links to docs.
- `docs/ARCHITECTURE.md`: system model, concepts, boundaries, invariants.
- `docs/EDGE.md`: direct and reverse tunnel connectivity guidance.
- `docs/DEVELOPER.md`: how to work in the repo and current implementation boundaries.
- `docs/SECURITY.md`: trust model, custody boundary, logging, and responsible usage.
- `docs/TESTING_STRATEGY.md`: test boundaries and what tests are expected to prove.
- `docs/ARCHITECTURAL_DECISIONS.md`: durable decisions and rationale.
- source files: local technical rationale, local invariants, implementation-specific details.

Do not put local implementation detail into high-level docs unless it is necessary to explain a boundary.

---

## Suggested Documentation Work

### Phase 1: Grounding

Inspect the code and make a short inventory:

- MCP tools currently exposed.
- Connection pool API and current mismatches.
- Discovery scripts currently present.
- Cache files or cache behavior currently present.
- Commands available to build, install, and test.
- Current docs that overstate or understate behavior.

Do not edit docs until this grounding pass is complete.

### Phase 2: Concept Alignment

Update documentation terminology consistently:

- Use “boundary agent” for the agent role.
- Use “remote capability environment” for connected machines where useful.
- Use “reverse tunnel mode” in prose.
- Preserve `mode: "tunnel"` when referring to current config values.
- Use “capability cache” for discovered per-connection knowledge.
- Use “orchestrator gets capability, not custody” to express the trust model.

### Phase 3: Documentation Rewrite

Improve the following files:

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/EDGE.md`
- `docs/DEVELOPER.md`
- `docs/SECURITY.md`
- `docs/TESTING_STRATEGY.md` if terminology or boundaries need adjustment
- `docs/ARCHITECTURAL_DECISIONS.md` if a durable decision should be recorded

Focus on clarity and structure, not volume.

### Phase 4: Validation

Validate that:

- all relative links work,
- docs do not reference files that do not exist,
- docs distinguish implemented behavior from intended architecture,
- docs do not claim reverse tunnel listener behavior exists,
- terminology is consistent,
- and README remains readable as a repo entry point.

Run tests if documentation changes are paired with code changes. If this slice only changes docs, still report that no code validation was required.

---

## Non-Goals

Do not implement new features in this documentation slice.

Do not:

- implement the reverse tunnel listener,
- implement capability cache,
- refactor connection pool code,
- add dependencies,
- add CI,
- introduce new orchestration frameworks,
- or add speculative architecture that is not grounded in the project direction.

Documentation may describe intended direction, but it must be clearly labeled as such.

---

## Expected Deliverable

Roo should produce:

- a concise summary of what was inspected,
- a list of documentation files updated,
- a short explanation of how the docs now frame the project,
- any implementation/documentation mismatches discovered,
- and recommended next slices.

Recommended next slices may include:

- dependency baseline cleanup,
- connection pool API cleanup,
- local SSH fixture and direct connection tests,
- capability discovery baseline,
- capability cache design,
- script execution primitive,
- file transfer primitive,
- reverse tunnel listener design.
