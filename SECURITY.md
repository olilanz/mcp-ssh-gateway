# Security Model

- Reverse SSH is the default and secure mode.
- Edge devices must never execute commands on the agent.
- No private keys are passed over MCP.
- Token-based auth is required for edge registration.
