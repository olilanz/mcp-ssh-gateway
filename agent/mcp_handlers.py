import logging
from typing import Optional

from mcp.server.fastmcp import FastMCP

def register_tools(mcp: FastMCP, node_service, agent_identity_service):

    @mcp.tool()
    def get_node_status() -> dict:
        logging.debug("get_node_status called")
        return node_service.get_node_status()

    @mcp.tool()
    def get_node_info(name: Optional[str] = None, refresh: bool = False) -> dict:
        logging.debug(f"get_node_info called: name={name}, refresh={refresh}")
        return node_service.get_node_info(name=name, refresh=refresh)

    @mcp.tool()
    def add_node(name: str, host: str, port: int = 22, user: str = "pi", password: str = "", mode: str = "direct") -> dict:
        logging.debug(f"add_node called: name={name}, host={host}, port={port}, user={user}, mode={mode}")
        return node_service.add_node(name=name, host=host, port=port, user=user, password=password, mode=mode)

    @mcp.tool()
    def remove_node(name: str) -> dict:
        logging.debug(f"remove_node called: name={name}")
        return node_service.remove_node(name=name)

    @mcp.tool()
    def enable_node(name: str, validate: bool = False) -> dict:
        logging.debug(f"enable_node called: name={name}, validate={validate}")
        return node_service.enable_node(name=name, validate=validate)

    @mcp.tool()
    def disable_node(name: str) -> dict:
        logging.debug(f"disable_node called: name={name}")
        return node_service.disable_node(name=name)

    # Legacy local execution primitives.
    # These tools operate on the gateway host, not on a named node.
    # They do not participate in the node-oriented API surface.
    # Future node execution will use node-scoped tools (e.g. run_command_on_node).
    # TODO: replace with node-oriented execution tools in a future slice.
    @mcp.tool()
    def run_command(params):
        import subprocess
        cmd = params.get("cmd")
        logging.debug(f"run_command called: {cmd}")
        try:
            result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
            return {"stdout": result.stdout, "stderr": result.stderr, "exit_code": result.returncode}
        except subprocess.CalledProcessError as e:
            return {"stdout": e.stdout, "stderr": e.stderr, "exit_code": e.returncode}

    @mcp.tool()
    def get_agent_public_key() -> dict:
        """Return the agent's SSH public key for installation on managed nodes."""
        identity = agent_identity_service.get_identity()
        return {
            "public_key": identity.public_key,
            "fingerprint": identity.fingerprint,
            "key_type": identity.key_type,
        }

    @mcp.tool()
    def upload_file(path, data_b64, mode="0644"):
        from agent.file_utils import write_file

        logging.debug(f"upload_file called for {path} with mode {mode}")
        write_file(path, data_b64, mode)
        return {"status": "written", "path": path}

    @mcp.tool()
    def run_command_on_node(name: str, command: str, timeout: int = 30) -> dict:
        logging.debug(f"run_command_on_node called: name={name}, command={command}, timeout={timeout}")
        return node_service.run_command_on_node(name=name, command=command, timeout=timeout)

    @mcp.tool()
    def upload_file_to_node(name: str, remote_path: str, data_b64: str, mode: str = "0644") -> dict:
        logging.debug(f"upload_file_to_node called: name={name}, remote_path={remote_path}, mode={mode}")
        return node_service.upload_file_to_node(name=name, remote_path=remote_path, data_b64=data_b64, mode=mode)

    @mcp.tool()
    def download_file_from_node(name: str, remote_path: str) -> dict:
        logging.debug(f"download_file_from_node called: name={name}, remote_path={remote_path}")
        return node_service.download_file_from_node(name=name, remote_path=remote_path)
