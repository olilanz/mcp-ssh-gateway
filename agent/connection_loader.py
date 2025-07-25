import logging
import json
import os
import sys

class ConnectionConfigError(Exception):
    """Raised when the connection configuration is invalid."""
    pass

def load_connections(path):
    """Load and validate the agent configuration from a JSON file."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"❌ Config file not found: {path}")

    with open(path, "r") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            raise ConnectionConfigError(f"❌ Invalid JSON format: {e}")

    if "connections" not in data or not isinstance(data["connections"], list):
        raise ConnectionConfigError("❌ Config must contain a top-level 'connections' list")

    seen_names = set()
    validated_connections = []

    for i, conn in enumerate(data["connections"]):
        context = f"[connections[{i}]]"
        name = conn.get("name")
        if not name or not isinstance(name, str):
            raise ConnectionConfigError(f"{context} Missing or invalid 'name'")
        if name in seen_names:
            raise ConnectionConfigError(f"{context} Duplicate connection name '{name}'")
        seen_names.add(name)

        user = conn.get("user")
        if not user or not isinstance(user, str):
            raise ConnectionConfigError(f"{context} Missing or invalid 'user'")

        id_file = conn.get("id_file")
        if not id_file or not isinstance(id_file, str):
            raise ConnectionConfigError(f"{context} Missing or invalid 'id_file'")
        if not os.path.isfile(id_file):
            logging.warning(f"⚠️ Warning: Identity file not found at path '{id_file}'")

        mode = conn.get("mode")
        if mode not in ("direct", "tunnel"):
            raise ConnectionConfigError(f"{context} Invalid 'mode'. Must be 'direct' or 'tunnel'")

        port = conn.get("port")
        if not isinstance(port, int) or not (1 <= port <= 65535):
            raise ConnectionConfigError(f"{context} Invalid or missing 'port' (must be 1–65535)")

        host = conn.get("host")
        if mode == "direct":
            if not host or not isinstance(host, str):
                raise ConnectionConfigError(f"{context} 'host' is required for mode 'direct'")

        validated_connections.append({
            "name": name,
            "user": user,
            "id_file": id_file,
            "mode": mode,
            "port": port,
            "host": host if mode == "direct" else None
        })

    logging.info(f"✅ Loaded {len(validated_connections)} connection(s) successfully from {path}")
    return validated_connections
