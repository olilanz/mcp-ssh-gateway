"""
Internal node model dataclasses for mcp-ssh-gateway.

Semantic model:
  node       = managed SSH-reachable execution environment (identity + config)
  connection = runtime SSH transport/session to a node
  pool       = runtime collection of connections and their lifecycle management

These three concepts are distinct. Node identity belongs to the node layer.
SSH mechanics belong to the connection/pool layer.

NodeRuntimeState is a computed DTO only — it is never persisted in NodeRegistry.
It is assembled at call time from two live sources:
  1. Registry: NodeConfig.enabled, NodeConfig.mode, etc.
  2. Pool: current ConnectionState queried directly from ConnectionPool at call time.

Bridging note:
  NodeConfig fields (host, port, user, id_file) are a temporary bridge from
  ConnectionConfig, populated at startup from the existing config format.
  The long-term direction is for SSH transport details to move toward OpenSSH
  config file entries, with NodeConfig holding only the node identity and
  management state. The id_file and raw host/port/user fields must not be
  treated as permanent fields of the node identity model.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class NodeConfig:
    """Identity and configuration of a managed node."""

    name: str
    mode: str        # "direct" | "tunnel"
    enabled: bool
    host: Optional[str]
    port: int
    user: str
    id_file: Optional[str]


@dataclass
class NodeInfoCache:
    """Cached discovered facts about a node."""

    facts: dict = field(default_factory=dict)
    collected_at: Optional[str] = None


@dataclass
class NodeRuntimeState:
    """Computed DTO — never stored in registry. Assembled at call time from registry + live pool state."""

    pool_state: str = "unknown"   # "open" | "closed" | "opening" | "broken" | "unknown"
    reachable: bool = False
    last_seen_at: Optional[str] = None   # ISO 8601 or null
    last_error: Optional[str] = None
