FROM ubuntu:24.04

# fundamental configuration
ENV SSH_LISTEN_PORT=22
ENV MCP_PORT=8000

# Install required packages
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
    openssh-server \
    curl \
    iproute2 \
    libffi-dev libssl-dev \
    python3-pip \
    git \
    && apt-get remove -y python3-jwt \
    && rm -rf /var/lib/apt/lists/*

    
# Configure SSH daemon during build
#RUN mkdir -p /etc/ssh && \
#    echo "Port ${SSH_LISTEN_PORT}" > /etc/ssh/sshd_config && \
#    echo "PermitRootLogin prohibit-password" >> /etc/ssh/sshd_config && \
#    echo "PasswordAuthentication no" >> /etc/ssh/sshd_config && \
#    echo "PermitEmptyPasswords no" >> /etc/ssh/sshd_config && \
#    echo "ChallengeResponseAuthentication no" >> /etc/ssh/sshd_config && \
#    echo "UsePAM no" >> /etc/ssh/sshd_config && \
#    echo "PermitTTY no" >> /etc/ssh/sshd_config && \
#    echo "ForceCommand echo 'This connection is for tunneling only. No command execution available.'" >> /etc/ssh/sshd_config && \
#    echo "GatewayPorts yes" >> /etc/ssh/sshd_config && \
#    echo "AllowTcpForwarding yes" >> /etc/ssh/sshd_config && \
#    echo "PermitOpen any" >> /etc/ssh/sshd_config && \
#    echo "AuthorizedKeysFile /etc/ssh/authorized_keys" >> /etc/ssh/sshd_config

WORKDIR /app
COPY pyproject.toml /app/pyproject.toml
COPY agent /app/agent
COPY app.py /app/app.py
RUN pip install --no-cache-dir --break-system-packages .

EXPOSE ${MCP_PORT}
EXPOSE ${SSH_LISTEN_PORT}

# ── Test isolation user ──────────────────────────────────────────────────────
# This Dockerfile serves two purposes:
#   1. Production runtime for the mcp-ssh-gateway agent (the main workload).
#   2. Development / CI container that runs the full test suite in-place.
#
# The `sshbootstrap` user exists solely to support functional tests for the
# add_node password-bootstrap flow (tests/functional/test_add_node_functional.py).
# The tests spawn an isolated sshd instance that accepts password auth only for
# this user, installs the agent's public key via SFTP, and then validates
# key-based login — without touching any production user account.
#
# This user MUST NOT be used for any production purpose.
# Its password is hard-coded and intentionally weak because it is only
# reachable from 127.0.0.1 inside an ephemeral test sshd instance.
RUN useradd -m -s /bin/sh sshbootstrap \
    && echo 'sshbootstrap:sshbootstrap' | chpasswd

COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

COPY scripts /app/scripts
RUN chmod +x /app/scripts/*.sh

ENTRYPOINT ["/app/entrypoint.sh"]
