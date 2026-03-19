import os
from contextlib import AsyncExitStack
from typing import Any, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

from app.core.config import settings


class RuntimeMCPService:
    def __init__(self):
        self._config_path = settings.MCP_CONFIG_PATH
        self._initialized = False
        self._exit_stack: Optional[AsyncExitStack] = None
        self._clients: dict[str, ClientSession] = {}
        self._lock = None

    async def call(self, function_name: str, function_args: dict[str, Any]) -> dict[str, Any]:
        if not function_name.strip():
            return {"success": False, "message": "function_name is required", "data": {}}
        await self._ensure_initialized()
        if not self._clients:
            return {"success": False, "message": "No MCP servers connected", "data": {}}

        server_name, original_tool_name = self._parse_function_name(function_name)
        if not server_name or not original_tool_name:
            return {"success": False, "message": f"Invalid mcp function name: {function_name}", "data": {}}

        session = self._clients.get(server_name)
        if session is None:
            return {"success": False, "message": f"MCP server not connected: {server_name}", "data": {}}

        try:
            result = await session.call_tool(original_tool_name, function_args or {})
            text_parts: list[str] = []
            if result and hasattr(result, "content") and result.content:
                for item in result.content:
                    text = getattr(item, "text", None)
                    if isinstance(text, str):
                        text_parts.append(text)
                    else:
                        text_parts.append(str(item))
            return {
                "success": True,
                "message": "ok",
                "data": {
                    "server": server_name,
                    "tool": original_tool_name,
                    "result": "\n".join(text_parts) if text_parts else "",
                },
            }
        except Exception as e:
            return {
                "success": False,
                "message": str(e),
                "data": {"server": server_name, "tool": original_tool_name},
            }

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        if not os.path.exists(self._config_path):
            self._initialized = True
            return

        import json
        from asyncio import Lock

        self._lock = Lock()
        self._exit_stack = AsyncExitStack()

        with open(self._config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        servers = config.get("mcpServers", {}) if isinstance(config, dict) else {}
        if not isinstance(servers, dict):
            self._initialized = True
            return

        for server_name, server_conf in servers.items():
            if not isinstance(server_conf, dict):
                continue
            if server_conf.get("enabled", True) is False:
                continue
            try:
                session = await self._connect_server(server_conf)
                if session is not None:
                    self._clients[str(server_name)] = session
            except Exception:
                continue

        self._initialized = True

    async def _connect_server(self, server_conf: dict[str, Any]) -> Optional[ClientSession]:
        assert self._exit_stack is not None

        transport = str(server_conf.get("transport") or "stdio").strip().lower()

        if transport == "stdio":
            command = server_conf.get("command")
            if not isinstance(command, str) or not command.strip():
                return None
            args = server_conf.get("args")
            if not isinstance(args, list):
                args = []
            env = server_conf.get("env")
            if not isinstance(env, dict):
                env = {}

            server_params = StdioServerParameters(
                command=command,
                args=[str(x) for x in args],
                env={**os.environ, **{str(k): str(v) for k, v in env.items()}},
            )
            read_stream, write_stream = await self._exit_stack.enter_async_context(stdio_client(server_params))
            session = await self._exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
            await session.initialize()
            return session

        if transport in {"sse", "http"}:
            url = server_conf.get("url")
            if not isinstance(url, str) or not url.strip():
                return None
            read_stream, write_stream = await self._exit_stack.enter_async_context(sse_client(url))
            session = await self._exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
            await session.initialize()
            return session

        if transport == "streamable-http":
            url = server_conf.get("url")
            if not isinstance(url, str) or not url.strip():
                return None
            headers = server_conf.get("headers")
            kwargs = {"url": url}
            if isinstance(headers, dict) and headers:
                kwargs["headers"] = {str(k): str(v) for k, v in headers.items()}
            streamable_transport = await self._exit_stack.enter_async_context(streamablehttp_client(**kwargs))
            if len(streamable_transport) == 3:
                read_stream, write_stream, _ = streamable_transport
            else:
                read_stream, write_stream = streamable_transport
            session = await self._exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
            await session.initialize()
            return session

        return None

    def _parse_function_name(self, function_name: str) -> tuple[Optional[str], Optional[str]]:
        name = function_name.strip()
        if not name:
            return None, None

        # Prefer exact server prefix matches against connected servers.
        server_candidates = list(self._clients.keys())
        server_candidates.sort(key=len, reverse=True)

        for server in server_candidates:
            prefixed = f"mcp_{server}_"
            direct = f"{server}_"
            if name.startswith(prefixed):
                return server, name[len(prefixed) :]
            if name.startswith(direct):
                return server, name[len(direct) :]

        # Fallback parser
        raw = name[4:] if name.startswith("mcp_") else name
        parts = raw.split("_")
        if len(parts) < 2:
            return None, None
        return parts[0], "_".join(parts[1:])


runtime_mcp_service = RuntimeMCPService()
