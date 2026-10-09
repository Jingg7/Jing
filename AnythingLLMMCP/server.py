"""AnythingLLM MCP Server (Streamable HTTP, dual protocol)."""

import json
import urllib.request

from mcp.server.mcpserver import MCPServer

BASE_URL = "http://localhost:3001/api"
API_KEY = "YOUR_ANYTHINGLLM_API_KEY"

server = MCPServer(
    name="anythingllm",
    version="1.0.0",
    instructions="访问本机 AnythingLLM 的 MCP Server",
)


def _get(path: str) -> dict:
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        headers={"Authorization": f"Bearer {API_KEY}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


@server.tool()
def first_workspace_files() -> dict:
    """提取第一个工作区的文件（文档）信息。"""
    workspaces = _get("/v1/workspaces").get("workspaces", [])
    if not workspaces:
        return {"error": "没有任何工作区"}

    ws = workspaces[0]
    detail = _get(f"/v1/workspace/{ws['slug']}").get("workspace", [])
    detail = detail[0] if detail else {}

    files = []
    for doc in detail.get("documents", []):
        try:
            meta = json.loads(doc.get("metadata") or "{}")
        except json.JSONDecodeError:
            meta = {}
        files.append(
            {
                "docId": doc.get("docId"),
                "filename": meta.get("title") or doc.get("filename"),
                "storedFile": doc.get("filename"),
                "path": doc.get("docpath"),
                "source": meta.get("docSource"),
                "originalLocation": meta.get("url"),
                "wordCount": meta.get("wordCount"),
                "tokenCount": meta.get("token_count_estimate"),
                "published": meta.get("published"),
                "pinned": doc.get("pinned"),
                "createdAt": doc.get("createdAt"),
            }
        )

    return {
        "workspace": {"name": detail.get("name") or ws.get("name"), "slug": ws.get("slug")},
        "fileCount": len(files),
        "files": files,
    }


if __name__ == "__main__":
    server.run("streamable-http", host="127.0.0.1", port=8000, streamable_http_path="/mcp")
