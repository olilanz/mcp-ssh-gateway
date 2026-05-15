"""
NodeRegistry — in-memory, thread-safe store for node configuration and info cache.

Each registry entry is a tuple of (NodeConfig, NodeInfoCache) keyed by node name.
NodeRuntimeState is NOT stored here — it is a computed DTO assembled at call time
from registry config and live pool state.

All public methods acquire a threading.Lock for safety under concurrent access.
"""

import threading

from agent.nodes.models import NodeConfig, NodeInfoCache


class NodeRegistry:
    """In-memory registry of all configured nodes.

    Stores (NodeConfig, NodeInfoCache) 2-tuples keyed by node name.
    Thread-safe via a single lock acquired on every public method.

    NodeRuntimeState is never stored here. It is a computed DTO assembled at
    call time by NodeService from registry config + live pool state.
    """

    def __init__(self) -> None:
        self._store: dict[str, tuple[NodeConfig, NodeInfoCache]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def add(self, config: NodeConfig) -> None:
        """Add a node with an empty NodeInfoCache.

        Raises ValueError if a node with the same name already exists.
        """
        with self._lock:
            if config.name in self._store:
                raise ValueError(f"Node already exists: {config.name!r}")
            self._store[config.name] = (config, NodeInfoCache())

    def remove(self, name: str) -> None:
        """Remove a node from the registry.

        Raises KeyError if the node is not found.
        """
        with self._lock:
            if name not in self._store:
                raise KeyError(name)
            del self._store[name]

    def update_config(self, name: str, config: NodeConfig) -> None:
        """Replace the NodeConfig for an existing node.

        Raises KeyError if the node is not found.
        """
        with self._lock:
            if name not in self._store:
                raise KeyError(name)
            _, cache = self._store[name]
            self._store[name] = (config, cache)

    def update_cache(self, name: str, cache: NodeInfoCache) -> None:
        """Replace the NodeInfoCache for an existing node.

        Raises KeyError if the node is not found.
        """
        with self._lock:
            if name not in self._store:
                raise KeyError(name)
            cfg, _ = self._store[name]
            self._store[name] = (cfg, cache)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get(self, name: str) -> tuple[NodeConfig, NodeInfoCache]:
        """Return the (NodeConfig, NodeInfoCache) 2-tuple for a node.

        Raises KeyError if the node is not found.
        """
        with self._lock:
            if name not in self._store:
                raise KeyError(name)
            return self._store[name]

    def all(self) -> list[tuple[NodeConfig, NodeInfoCache]]:
        """Return all entries as a list of (NodeConfig, NodeInfoCache) 2-tuples."""
        with self._lock:
            return list(self._store.values())

    def exists(self, name: str) -> bool:
        """Return True if a node with the given name is registered."""
        with self._lock:
            return name in self._store
