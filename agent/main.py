import logging
from mcp.agent import Agent
from agent import mcp_handlers

def run_agent(config):
    logging.info("Initializing MCP agent...")

    agent = Agent(name="mcp-ssh-gateway")

    # Register supported MCP methods
    agent.register("get_status", mcp_handlers.get_status)
    agent.register("get_device_info", mcp_handlers.get_device_info)
    agent.register("run_command", mcp_handlers.run_command)
    agent.register("upload_file", mcp_handlers.upload_file)
    agent.register("get_agent_pubkey", mcp_handlers.get_agent_pubkey)
    agent.register("register_edge_key", mcp_handlers.register_edge_key)

    logging.info("Agent registered all handlers. Starting MCP loop.")
    agent.run()
