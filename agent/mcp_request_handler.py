import json
from agent import mcp_handlers

def handle_mcp_request(raw_line):
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
            response = {"jsonrpc": "2.0", "error": {"code": -32601, "message": "Method not found"}, "id": id_}

    except Exception as e:
        response = {"jsonrpc": "2.0", "error": {"code": -32000, "message": str(e)}, "id": None}

    print(json.dumps(response), flush=True)