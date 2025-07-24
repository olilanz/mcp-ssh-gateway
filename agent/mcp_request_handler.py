import json
from agent import mcp_handlers

def handle_mcp_request(raw_line):
    def json_rpc_error(code, message, id_=None):
        return {"jsonrpc": "2.0", "error": {"code": code, "message": message}, "id": id_}

    try:
        request = json.loads(raw_line)
        method = request.get("method")
        params = request.get("params", {})
        id_ = request.get("id")

        if not method:
            raise ValueError("Missing 'method' field")

        if hasattr(mcp_handlers, method):
            result = getattr(mcp_handlers, method)(**params)
            response = {"jsonrpc": "2.0", "result": result, "id": id_}
        else:
            response = json_rpc_error(-32601, "Method not found", id_)
    except Exception as e:
        response = json_rpc_error(-32000, str(e))

    print(json.dumps(response), flush=True)