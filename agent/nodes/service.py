"""
NodeService — business logic layer for node management.

Semantic model:
  node       = managed SSH-reachable execution environment (identity + config)
  connection = runtime SSH transport/session to a node
  pool       = runtime collection of connections and their lifecycle management

NodeService composes NodeRuntimeState at call time from two live sources:
  1. Registry: NodeConfig + NodeInfoCache (identity, config, cached facts)
  2. Pool: current ConnectionState queried via pool.get_connection_state() at call time

NodeRuntimeState is assembled inline and NEVER stored in the registry.
The pool_state field is always freshly derived from the pool at call time.
"""

from dataclasses import replace
from typing import Optional

from agent.connectionpool.pool import ConnectionPool
from agent.nodes.registry import NodeRegistry


class NodeService:
    """Service layer for node management operations.

    Reads node identity and cached info from the registry.
    Derives live pool state from the ConnectionPool at call time.
    Never copies or caches pool runtime state into the registry.

    Phase 3 implements read-only methods only:
      - get_node_status()
      - get_node_info(name, refresh)

    Phase 4 adds mutation methods:
      - disable_node(name)
      - enable_node(name, validate)
      - remove_node(name)
      - add_node(name, host, port, user, password, mode)
    """

    def __init__(self, registry: NodeRegistry, pool: ConnectionPool) -> None:
        self._registry = registry
        self._pool = pool

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _derive_pool_state(self, name: str) -> str:
        """Query pool at call time and return a pool_state string.

        Returns one of: "open", "closed", "opening", "broken", "not_in_pool".
        This is always freshly computed — never read from the registry.
        Delegates to pool.get_connection_state(name); does not access pool internals directly.
        """
        return self._pool.get_connection_state(name)

    def _node_entry_for_status(self, config, cache) -> dict:
        """Assemble one node entry for get_node_status() response.

        Reads config + cache from registry arguments; derives pool_state live.
        """
        pool_state = self._derive_pool_state(config.name)
        reachable = pool_state == "open"

        last_seen_at = cache.facts.get("last_seen_at") if cache.facts else None
        last_error = cache.facts.get("last_error") if cache.facts else None
        cached_info_available = bool(cache.facts)

        return {
            "name": config.name,
            "mode": config.mode,
            "enabled": config.enabled,
            "configured": True,
            "pool_state": pool_state,
            "reachable": reachable,
            "last_seen_at": last_seen_at,
            "last_error": last_error,
            "cached_info_available": cached_info_available,
        }

    def _node_entry_for_info(self, config, cache) -> dict:
        """Assemble one node entry for get_node_info() response.

        Reads config + cache from registry arguments; derives pool_state live.
        """
        pool_state = self._derive_pool_state(config.name)
        return {
            "name": config.name,
            "enabled": config.enabled,
            "pool_state": pool_state,
            "info": dict(cache.facts),
        }

    # ------------------------------------------------------------------
    # Read APIs (Phase 3)
    # ------------------------------------------------------------------

    def get_node_status(self) -> dict:
        """Return gateway status and all configured nodes with live pool state.

        Reads node config and cache from the registry.
        Derives pool_state at call time via pool.get_connection_state().
        Never copies or caches pool runtime state into the registry.

        Returns:
            {"status": "ok", "nodes": [...]} with one entry per configured node.
            Empty registry returns {"status": "ok", "nodes": []}.
        """
        entries = self._registry.all()
        nodes = [self._node_entry_for_status(cfg, cache) for cfg, cache in entries]
        return {"status": "ok", "nodes": nodes}

    def get_node_info(
        self,
        name: Optional[str] = None,
        refresh: bool = False,
    ) -> dict:
        """Return configured info, cached facts, and current pool state per node.

        Args:
            name:    Optional node name. If None, returns info for all nodes.
            refresh: If True, live SSH refresh is intended but NOT YET IMPLEMENTED.
                     In this phase, refresh=True returns the same data as refresh=False
                     plus a "refresh_note" field indicating the stub.

        Returns:
            {"nodes": [...]} with one entry per returned node.
            Unknown name: {"error": "node not found", "name": "<name>"}.
        """
        if name is not None:
            if not self._registry.exists(name):
                return {"error": "node not found", "name": name}
            config, cache = self._registry.get(name)
            entries = [(config, cache)]
        else:
            entries = self._registry.all()

        nodes = [self._node_entry_for_info(cfg, cache) for cfg, cache in entries]
        result: dict = {"nodes": nodes}

        if refresh:
            result["refresh_note"] = "live refresh not yet implemented"

        return result

    # ------------------------------------------------------------------
    # Mutation APIs (Phase 4)
    # ------------------------------------------------------------------

    def disable_node(self, name: str) -> dict:
        """Disable a configured node and close its pool connection.

        Sets enabled=False on the node's NodeConfig in the registry.
        Calls pool.disable_connection(name) to close and prevent reconnect.

        Returns:
            {"status": "disabled", "name": name} on success.
            {"error": "node not found", "name": name} if unknown.
        """
        if not self._registry.exists(name):
            return {"error": "node not found", "name": name}

        existing_cfg, _ = self._registry.get(name)
        updated_cfg = replace(existing_cfg, enabled=False)
        self._registry.update_config(name, updated_cfg)
        self._pool.disable_connection(name)
        return {"status": "disabled", "name": name}

    def enable_node(self, name: str, validate: bool = False) -> dict:
        """Enable a configured node and allow its pool connection to reconnect.

        Sets enabled=True on the node's NodeConfig in the registry.
        Calls pool.enable_connection(name) to allow reconnect (does not immediately open).

        Args:
            name:     Node name.
            validate: If True, validation is acknowledged but NOT YET IMPLEMENTED.

        Returns:
            {"status": "enabled", "name": name} on success.
            Adds "validate_note" key if validate=True.
            {"error": "node not found", "name": name} if unknown.
        """
        if not self._registry.exists(name):
            return {"error": "node not found", "name": name}

        existing_cfg, _ = self._registry.get(name)
        updated_cfg = replace(existing_cfg, enabled=True)
        self._registry.update_config(name, updated_cfg)
        self._pool.enable_connection(name)

        result: dict = {"status": "enabled", "name": name}
        if validate:
            result["validate_note"] = "validation not yet implemented"
        return result

    def remove_node(self, name: str) -> dict:
        """Remove a node from the pool and registry entirely.

        Calls pool.remove_connection(name) to close and remove from pool.
        Calls registry.remove(name) to remove from registry.

        Returns:
            {"status": "removed", "name": name} on success.
            {"error": "node not found", "name": name} if unknown.
        """
        if not self._registry.exists(name):
            return {"error": "node not found", "name": name}

        self._pool.remove_connection(name)
        self._registry.remove(name)
        return {"status": "removed", "name": name}

    def add_node(
        self,
        name: str,
        host: str,
        port: int,
        user: str,
        password: str,
        mode: str = "direct",
    ) -> dict:
        """Add a new node to the gateway (bootstrap not yet implemented).

        Bootstrap is not implemented: this method does NOT add the node to the
        registry and does NOT attempt any SSH connection.

        Credential safety contract (NON-NEGOTIABLE):
          - password is accepted as a parameter for API compatibility only
          - password intentionally not used - bootstrap not implemented
          - password is never assigned to any variable, never logged, never returned,
            never stored in any object or registry

        Returns:
            {"status": "bootstrap_not_implemented", "name": name,
             "reason": "password-based bootstrap is not implemented in this slice"}
        """
        # password intentionally not used - bootstrap not implemented
        return {
            "status": "bootstrap_not_implemented",
            "name": name,
            "reason": "password-based bootstrap is not implemented in this slice",
        }
