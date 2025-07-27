FROM ubuntu:24.04

# fundamental configuration
ENV SSH_LISTEN_PORT=22
ENV MCPO_PORT=8000

# Install required packages
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
    openssh-server \
    libffi-dev libssl-dev \
    python3-pip \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --break-system-packages mcp[cli] mcpo pytest paramiko

# Configure SSH daemon during build
RUN mkdir -p /etc/ssh && \
    echo "Port ${SSH_LISTEN_PORT}" > /etc/ssh/sshd_config && \
    echo "PermitRootLogin prohibit-password" >> /etc/ssh/sshd_config && \
    echo "PasswordAuthentication no" >> /etc/ssh/sshd_config && \
    echo "PermitEmptyPasswords no" >> /etc/ssh/sshd_config && \
    echo "ChallengeResponseAuthentication no" >> /etc/ssh/sshd_config && \
    echo "UsePAM no" >> /etc/ssh/sshd_config && \
    echo "PermitTTY no" >> /etc/ssh/sshd_config && \
    echo "ForceCommand echo 'This connection is for tunneling only. No command execution available.'" >> /etc/ssh/sshd_config && \
    echo "GatewayPorts yes" >> /etc/ssh/sshd_config && \
    echo "AllowTcpForwarding yes" >> /etc/ssh/sshd_config && \
    echo "PermitOpen any" >> /etc/ssh/sshd_config && \
    echo "AuthorizedKeysFile /etc/ssh/authorized_keys" >> /etc/ssh/sshd_config

# environment setup
EXPOSE ${MCPO_PORT}
EXPOSE ${SSH_LISTEN_PORT}

# startup script
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# application code
COPY app.py /app/app.py
COPY agent /app/agent

# helper scripts
COPY scripts /app/scripts
RUN chmod +x /app/scripts/*.sh

# Default entrypoint
WORKDIR /app
ENTRYPOINT ["/app/entrypoint.sh"]
