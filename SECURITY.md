# Security Policy

## 📢 Reporting a Vulnerability

If you discover a security vulnerability in `mcp-ssh-gateway`, please **do not open a public issue**.

Instead, contact the project maintainer **privately** to allow for responsible disclosure and a coordinated fix.

Email: [security@yourdomain.example]  
(Replace with actual contact address if available.)

---

## 🔒 Supported Versions

| Version | Supported |
|---------|-----------|
| 0.x     | ✅ Yes     |

We aim to patch critical security issues in the latest major version. Older versions may not receive security updates.

---

## ✅ Security by Design

`mcp-ssh-gateway` is designed with the following principles:

- Reverse SSH only: edge devices initiate connections
- No command execution allowed on the agent
- Strict key-based authentication
- Audit-friendly: deterministic, observable behavior
- Secure by default: no open ports on edge systems

---

## 🛡 Security Best Practices

To further protect your deployment:

- Run in isolated Docker containers or sandboxed environments
- Rotate SSH keys periodically
- Monitor outbound connections from edge devices
- Limit LLM instructions to audited prompts

---

Thank you for contributing to a safer open-source ecosystem!
