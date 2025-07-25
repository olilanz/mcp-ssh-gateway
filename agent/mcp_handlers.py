import logging

from mcp.server.fastmcp import FastMCP

def register_tools(mcp: FastMCP):

    @mcp.tool()
    def get_status(params):
        logging.debug("get_status called")
        return {"status": "ok"}

    @mcp.tool("get_device_info")
    def get_device_info(params):
        import platform
        logging.debug("get_device_info called")
        return {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine()
        }

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
    def upload_file(path, data_b64, mode="0644"):
        from agent.file_utils import write_file

        logging.debug(f"upload_file called for {path} with mode {mode}")
        write_file(path, data_b64, mode)
        return {"status": "written", "path": path}

