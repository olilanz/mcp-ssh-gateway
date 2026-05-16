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
from dataclasses import dataclass as _dataclass
from typing import Optional

from agent.connectionpool.pool import ConnectionPool
from agent.nodes.registry import NodeRegistry


@_dataclass
class _NodeReady:
    """Internal result from ensure_node_ready. Never returned through MCP.

    Contains an open Connection instance ready for execution.
    Callers check isinstance(result, dict) to detect error — if not dict, it's _NodeReady.
    """
    connection: object


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

    def __init__(self, registry: NodeRegistry, pool: ConnectionPool, handshake_service=None, agent_identity_service=None) -> None:  # noqa: keep signature backward-compat for now; Fix D enforced via conftest
        self._registry = registry
        self._pool = pool
        # Import here to avoid circular imports at module level if needed
        from agent.nodes.handshake import NodeHandshakeService
        self._handshake_service = handshake_service or NodeHandshakeService()
        self._identity_service = agent_identity_service

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
            refresh: If True, perform a live SSH handshake refresh for the named node.
                     name must be provided when refresh=True.

        Returns:
            {"nodes": [...]} with one entry per returned node.
            Unknown name (refresh=False): {"error": "node not found", "name": "<name>"}.
            Unknown name (refresh=True): {"error": "not_found", "name": "<name>"}.
            refresh=True without name: {"error": "refresh_target_required", "reason": "..."}.
        """
        from agent.nodes.models import NodeInfoCache

        # Step 1: refresh=True requires a name
        if refresh and name is None:
            return {
                "error": "refresh_target_required",
                "reason": "Specify a node name when refresh=true",
            }

        # Step 2: named node lookup (refresh=True or refresh=False)
        if name is not None:
            if not self._registry.exists(name):
                if refresh:
                    return {"error": "not_found", "name": name}
                return {"error": "node not found", "name": name}
            config, cache = self._registry.get(name)

            # Disabled guard — only enforced on refresh path
            if refresh and not config.enabled:
                return {"error": "node_disabled", "name": name}

            # Step 3: live SSH refresh
            if refresh:
                conn_obj = self._pool.get_connection(name)
                if conn_obj is None:
                    return {"error": "not_in_pool", "name": name}

                conn = self._pool.ensure_connection_open(name)
                if conn is None:
                    return {"error": "connection_not_open", "name": name}

                facts = self._handshake_service.run(conn, timeout=10)
                if facts:
                    new_cache = NodeInfoCache(facts=facts)
                    self._registry.update_cache(name, new_cache)
                    _, cache = self._registry.get(name)  # re-fetch updated cache
                    return {
                        "nodes": [self._node_entry_for_info(config, cache)],
                        "refreshed": [name],
                        "refresh_failed": {},
                    }
                else:
                    # Handshake returned empty — return stale cache with marker
                    return {
                        "nodes": [self._node_entry_for_info(config, cache)],
                        "refreshed": [],
                        "refresh_failed": {name: "handshake_returned_empty"},
                    }

            # Step 4 (refresh=False): single named node, normal read
            entries = [(config, cache)]
        else:
            # Step 4 (refresh=False): all nodes
            entries = self._registry.all()

        nodes = [self._node_entry_for_info(cfg, cache) for cfg, cache in entries]
        return {"nodes": nodes}

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

        If validate=True, probes connectivity and runs the SSH handshake after enabling.
        Validation failure NEVER reverts the node to disabled — validated=False is a probe
        result, not a gate.

        Args:
            name:     Node name.
            validate: If True, probe connectivity and run SSH handshake after enabling.

        Returns:
            validate=False: {"status": "enabled", "name": name, "validated": False}
            validate=True success: {"status": "enabled", "name": name, "validated": True}
            validate=True probe failure: {"status": "enabled", "name": name,
                                          "validated": False, "error": "<reason>"}
            Unknown node: {"error": "not_found", "name": name}
        """
        from agent.nodes.models import NodeInfoCache

        # Step 1: Guard
        if not self._registry.exists(name):
            return {"error": "not_found", "name": name}

        # Step 2: Enable the node (same for both validate paths)
        existing_cfg, _ = self._registry.get(name)
        updated_cfg = replace(existing_cfg, enabled=True)
        self._registry.update_config(name, updated_cfg)
        self._pool.enable_connection(name)

        if not validate:
            return {"status": "enabled", "name": name, "validated": False}

        # Step 3: Probe connectivity
        conn_obj = self._pool.get_connection(name)
        if conn_obj is None:
            return {
                "status": "enabled",
                "name": name,
                "validated": False,
                "error": "not_in_pool",
            }

        conn = self._pool.ensure_connection_open(name)
        if conn is None:
            return {
                "status": "enabled",
                "name": name,
                "validated": False,
                "error": "connection_not_open",
            }

        # Step 4: Probe handshake — update cache on success
        facts = self._handshake_service.run(conn, timeout=10)
        if facts:
            new_cache = NodeInfoCache(facts=facts)
            self._registry.update_cache(name, new_cache)
            return {
                "status": "enabled",
                "name": name,
                "validated": True,
            }
        else:
            return {
                "status": "enabled",
                "name": name,
                "validated": False,
                "error": "handshake_failed",
            }

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
        """Bootstrap a new node into the gateway using password-based SSH key installation.

        Credential safety contract (NON-NEGOTIABLE):
          - password is used ONLY for the one-shot paramiko connection in Step 2
          - password is NEVER assigned to any config, registry entry, log message, or return value
          - password is not stored beyond the local scope of the pw_client.connect() call

        Parameters:
            name:     Unique node name.
            host:     SSH hostname or IP.
            port:     SSH port.
            user:     SSH username.
            password: Bootstrap password — used only to install agent public key.
            mode:     Connection mode. Only "direct" is supported.

        Returns:
            {"status": "added", "name": name, "validated": True} on success.
            Various {"error": ...} dicts on failure (see individual steps below).
        """
        import logging
        import paramiko
        from agent.connectionpool.config_loader import ConnectionConfig
        from agent.nodes.models import NodeConfig

        # Step 0: mode guard
        if mode != "direct":
            return {
                "error": "unsupported_mode",
                "mode": mode,
                "reason": "assisted tunnel onboarding is not implemented",
            }

        # Step 1: duplicate guard
        if self._registry.exists(name):
            return {"error": "node_already_exists", "name": name}

        # Step 2: password-based connection
        pw_client = paramiko.SSHClient()
        pw_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            # password used here and nowhere else
            pw_client.connect(host, port=port, username=user, password=password, timeout=15)
        except Exception as exc:
            try:
                pw_client.close()
            except Exception:
                pass
            return {"error": "password_connect_failed", "name": name, "detail": str(exc)}

        # Step 3: retrieve agent public key and private key path — password is no longer referenced below
        try:
            if self._identity_service is None:
                raise RuntimeError("identity service is not configured")
            identity = self._identity_service.get_identity()
            key_line = identity.public_key
            private_key_path = identity.private_key_path
        except Exception:
            try:
                pw_client.close()
            except Exception:
                pass
            return {"error": "identity_not_available", "name": name}

        # Step 4: install public key via SFTP (idempotent, no shell injection)
        try:
            sftp = pw_client.open_sftp()
            try:
                home_dir = sftp.normalize(".")
                ssh_dir = f"{home_dir}/.ssh"
                auth_keys_path = f"{ssh_dir}/authorized_keys"

                # Ensure ~/.ssh directory exists
                try:
                    sftp.stat(ssh_dir)
                except FileNotFoundError:
                    sftp.mkdir(ssh_dir)
                    sftp.chmod(ssh_dir, 0o700)

                # Read existing authorized_keys content (create if missing)
                try:
                    with sftp.file(auth_keys_path, "r") as fh:
                        existing = fh.read().decode("utf-8", errors="replace")
                except (FileNotFoundError, IOError):
                    existing = ""

                # Idempotent: only append if key_line is not already present
                if key_line not in existing:
                    new_content = existing
                    if new_content and not new_content.endswith("\n"):
                        new_content += "\n"
                    new_content += key_line + "\n"
                    with sftp.file(auth_keys_path, "w") as fh:
                        fh.write(new_content.encode("utf-8"))
                    sftp.chmod(auth_keys_path, 0o600)
            finally:
                sftp.close()
        except Exception as exc:
            try:
                pw_client.close()
            except Exception:
                pass
            return {"error": "authorized_keys_write_failed", "name": name, "detail": str(exc)}

        # Step 5: close password connection
        try:
            pw_client.close()
        except Exception:
            pass

        # Step 6: add to pool (no password — key-based from here)
        config = ConnectionConfig(
            name=name,
            host=host,
            port=port,
            user=user,
            mode="direct",
            id_file=private_key_path,
        )
        self._pool.add_connection(config)

        # Step 7: validate key-based connection
        conn = self._pool.ensure_connection_open(name)
        if conn is None:
            self._pool.remove_connection(name)  # rollback pool entry
            return {"error": "key_auth_failed", "name": name}

        # Step 8: commit to registry — only reached on full success
        node_config = NodeConfig(
            name=name,
            host=host,
            port=port,
            user=user,
            mode="direct",
            enabled=True,
            id_file=private_key_path,
        )
        self._registry.add(node_config)
        return {"status": "added", "name": name, "validated": True}

    # ------------------------------------------------------------------
    # Node readiness (execution pre-flight)
    # ------------------------------------------------------------------

    def ensure_node_ready(self, name: str):
        """Verify node is known, enabled, reachable, and has handshake facts.

        Returns:
            _NodeReady(connection=...) on success — INTERNAL ONLY, never returned via MCP.
            {"error": "node not found",      "name": name} if not in registry.
            {"error": "node_disabled",       "name": name} if disabled.
            {"error": "not_in_pool",         "name": name} if not in pool.
            {"error": "connection_not_open", "name": name} if pool cannot open it.
        """
        # 1. Registry guard
        if not self._registry.exists(name):
            return {"error": "node not found", "name": name}
        config, cache = self._registry.get(name)

        # 2. Enabled guard
        if not config.enabled:
            return {"error": "node_disabled", "name": name}

        # 3. Pool presence guard (distinguishes not_in_pool from connection_not_open)
        conn = self._pool.get_connection(name)
        if conn is None:
            return {"error": "not_in_pool", "name": name}

        # 4. Open guard
        conn = self._pool.ensure_connection_open(name)
        if conn is None:
            return {"error": "connection_not_open", "name": name}

        # 5. Handshake (if cache is empty)
        if not cache.facts:
            facts = self._handshake_service.run(conn)
            if facts:
                from datetime import datetime, timezone
                from agent.nodes.models import NodeInfoCache
                new_cache = NodeInfoCache(
                    facts=facts,
                    collected_at=datetime.now(timezone.utc).isoformat(),
                )
                self._registry.update_cache(name, new_cache)

        return _NodeReady(connection=conn)

    # ------------------------------------------------------------------
    # Execution APIs (Phase 5)
    # ------------------------------------------------------------------

    def run_command_on_node(self, name: str, command: str, timeout: int = 30) -> dict:
        """Execute a command on a named node.

        Args:
            name:    Registered node name.
            command: Shell command string.
            timeout: Maximum seconds to wait for execution. Default 30.

        Returns:
            CommandResult.to_dict() on success.
            {"error": "...", "name": name} on guard failure or timeout.
        """
        ready = self.ensure_node_ready(name)
        if isinstance(ready, dict):
            return ready

        try:
            result = ready.connection.execute(command, timeout=timeout)
            return result.to_dict()
        except TimeoutError:
            return {"error": "timeout", "name": name, "command": command}

    # ------------------------------------------------------------------
    # File transfer APIs (Phase 6)
    # ------------------------------------------------------------------

    def upload_file_to_node(self, name: str, remote_path: str, data_b64: str, mode: str = "0644") -> dict:
        """Upload a base64-encoded file to a named node.

        Args:
            name:        Registered node name.
            remote_path: Absolute path on the remote node.
            data_b64:    Base64-encoded file content.
            mode:        Unix permission mode string. Default "0644".

        Returns:
            {"status": "written", "path": remote_path} on success.
            Error dict on guard failure or upload error.
        """
        ready = self.ensure_node_ready(name)
        if isinstance(ready, dict):
            return ready
        return ready.connection.upload_file(remote_path, data_b64, mode)

    def download_file_from_node(self, name: str, remote_path: str) -> dict:
        """Download a file from a named node, returning base64-encoded content.

        Args:
            name:        Registered node name.
            remote_path: Absolute path on the remote node.

        Returns:
            {"status": "ok", "path": remote_path, "data_b64": "..."} on success.
            Error dict on guard failure or download error.
        """
        ready = self.ensure_node_ready(name)
        if isinstance(ready, dict):
            return ready
        return ready.connection.download_file(remote_path)
