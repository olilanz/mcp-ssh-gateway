FROM ubuntu:24.04

# Install required packages
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
    openssh-server \
    python3-pip \
    python3-venv \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create working directory and virtual environment
WORKDIR /app
RUN python3 -m venv /opt/venv

# Activate venv and install mcpo inside
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir mcp-agent mcpo

# Copy application code
COPY ./app.py /app
COPY ./agent /app/agent
COPY ./scripts /app/scripts
COPY entrypoint.sh /entrypoint.sh

# Ensure entrypoint is executable
RUN chmod +x /entrypoint.sh

# fundamental configuration
ENV GATEWAY_MODE=inbound
ENV SSH_LISTEN_PORT=22
ENV SSH_REVERSE_PORT=2222
ENV MCPO_PORT=8000

EXPOSE ${MCPO_PORT}
EXPOSE ${SSH_PORT}

# Default entrypoint
ENTRYPOINT ["/entrypoint.sh"]
