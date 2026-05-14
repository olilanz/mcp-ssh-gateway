# Security Policy

## 📢 Reporting a Vulnerability

If you discover a security vulnerability in `mcp-ssh-gateway`, please **do not open a public issue**.

Instead, contact the project maintainer **privately** to allow for responsible disclosure and a coordinated fix.

Email: [security@yourdomain.example]

---

## 🔒 Supported Versions

| Version | Supported |
|---------|-----------|
| 0.x     | ✅ Yes     |

We aim to patch critical security issues in the latest major version. Older versions may not receive security updates.

---

## ✅ Security by Design

`mcp-ssh-gateway` is designed with the following principles:

- Direct SSH and tunnel-probing support with key-based auth
- No command execution allowed on the agent
- Strict key-based authentication
- Audit-friendly: deterministic, observable behavior
- Tunnel listener/server behavior is not implemented in current code

---

## 🛡 Security Best Practices

To further protect your deployment:

- Run in isolated Docker containers or sandboxed environments
- Rotate SSH keys periodically
- Monitor outbound connections from edge devices
- Limit LLM instructions to audited prompts

---

Thank you for contributing to a safer open-source ecosystem!
