from __future__ import annotations

from typing import Optional

from langchain.tools import tool

from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseToolkit
from app.domain.services.tools.local_api_client import local_sandbox_api_client


class FileToolkit(BaseToolkit):
    name: str = "file"

    @tool(parse_docstring=True)
    async def file_read(
        self,
        file: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        sudo: Optional[bool] = False,
    ) -> ToolResult:
        """Read file content.

        Args:
            file: Absolute file path.
            start_line: Optional start line (0-based).
            end_line: Optional end line (exclusive).
            sudo: Optional sudo flag.
        """
        result = await local_sandbox_api_client.post(
            "/api/v1/file/read",
            {"file": file, "start_line": start_line, "end_line": end_line, "sudo": sudo},
        )
        return ToolResult(**result)

    @tool(parse_docstring=True)
    async def file_write(
        self,
        file: str,
        content: str,
        append: Optional[bool] = False,
        leading_newline: Optional[bool] = False,
        trailing_newline: Optional[bool] = False,
        sudo: Optional[bool] = False,
    ) -> ToolResult:
        """Write or append file content.

        Args:
            file: Absolute file path.
            content: Text content.
            append: Whether to append.
            leading_newline: Add leading newline.
            trailing_newline: Add trailing newline.
            sudo: Optional sudo flag.
        """
        result = await local_sandbox_api_client.post(
            "/api/v1/file/write",
            {
                "file": file,
                "content": content,
                "append": append,
                "leading_newline": leading_newline,
                "trailing_newline": trailing_newline,
                "sudo": sudo,
            },
        )
        return ToolResult(**result)

    @tool(parse_docstring=True)
    async def file_str_replace(
        self,
        file: str,
        old_str: str,
        new_str: str,
        sudo: Optional[bool] = False,
    ) -> ToolResult:
        """Replace text in file.

        Args:
            file: Absolute file path.
            old_str: Source text.
            new_str: Replacement text.
            sudo: Optional sudo flag.
        """
        result = await local_sandbox_api_client.post(
            "/api/v1/file/replace",
            {"file": file, "old_str": old_str, "new_str": new_str, "sudo": sudo},
        )
        return ToolResult(**result)

    @tool(parse_docstring=True)
    async def file_find_in_content(self, file: str, regex: str, sudo: Optional[bool] = False) -> ToolResult:
        """Search content in file by regex.

        Args:
            file: Absolute file path.
            regex: Regex pattern.
            sudo: Optional sudo flag.
        """
        result = await local_sandbox_api_client.post(
            "/api/v1/file/search",
            {"file": file, "regex": regex, "sudo": sudo},
        )
        return ToolResult(**result)

    @tool(parse_docstring=True)
    async def file_find_by_name(self, path: str, glob: str) -> ToolResult:
        """Find files by glob.

        Args:
            path: Absolute directory path.
            glob: Glob pattern.
        """
        result = await local_sandbox_api_client.post(
            "/api/v1/file/find",
            {"path": path, "glob": glob},
        )
        return ToolResult(**result)
