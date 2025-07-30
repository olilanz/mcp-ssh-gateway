import json
import os
import logging
from dataclasses import dataclass
from typing import Optional
from enum import Enum

class ConnectionMode(Enum):
    DIRECT = "direct"
    TUNNEL = "tunnel"

class ConnectionConfigError(Exception):
    """Raised when the connection configuration is invalid."""
    pass

@dataclass
class ConnectionConfig:
    name: str
    user: str
    id_file: str
    mode: str  # either "direct" or "tunnel"
    port: int
    host: Optional[str]  # required for 'direct', None for 'tunnel'

def load_connections(path: str) -> list[dict]:
    """Load connection configurations from a file."""
    if not path or not os.path.exists(path):
        logging.warning("No valid config file provided. Returning an empty connection list.")
        return []

    with open(path, "r") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            raise ConnectionConfigError(f"❌ Invalid JSON format: {e}")

    if "connections" not in data or not isinstance(data["connections"], list):
        raise ConnectionConfigError("❌ Config must contain a top-level 'connections' list")

    return data["connections"]

def parse_connections(raw_connections: list[dict]) -> list[ConnectionConfig]:
    """Parse and validate raw connection configurations."""
    seen_names = set()
    validated = []

    for i, conn in enumerate(raw_connections):
        ctx = f"[connections[{i}]]"
        name = conn.get("name")
        if not name or not isinstance(name, str):
            raise ConnectionConfigError(f"{ctx} Missing or invalid 'name'")
        if name in seen_names:
            raise ConnectionConfigError(f"{ctx} Duplicate name '{name}'")
        seen_names.add(name)

        user = conn.get("user")
        if not user or not isinstance(user, str):
            raise ConnectionConfigError(f"{ctx} Missing or invalid 'user'")

        id_file = conn.get("id_file")
        if not id_file or not isinstance(id_file, str):
            raise ConnectionConfigError(f"{ctx} Missing or invalid 'id_file'")
        if not os.path.isfile(id_file):
            logging.warning(f"⚠️ Warning: Identity file not found at '{id_file}'")

        mode = conn.get("mode")
        if mode not in ("direct", "tunnel"):
            raise ConnectionConfigError(f"{ctx} Invalid mode '{mode}'")

        port = conn.get("port")
        if not isinstance(port, int) or not (1 <= port <= 65535):
            raise ConnectionConfigError(f"{ctx} Invalid or missing 'port'")

        host = conn.get("host")
        if mode == "direct":
            if not host or not isinstance(host, str):
                raise ConnectionConfigError(f"{ctx} 'host' is required for mode 'direct'")

        validated.append(ConnectionConfig(
            name=name,
            user=user,
            id_file=id_file,
            mode=mode,
            port=port,
            host=host if mode == "direct" else None
        ))

    logging.info(f"✅ Parsed {len(validated)} connection(s).")
    return validated

def load_and_parse_connections(path: str) -> list[ConnectionConfig]:
    """Load and parse connection configurations from a file."""
    raw_connections = load_connections(path)
    return parse_connections(raw_connections)