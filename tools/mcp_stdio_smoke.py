"""Process-level smoke test for the installed MapU MCP stdio server."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


REQUIRED_TOOLS = {
    "create_corpus",
    "list_corpora",
    "ingest_document",
    "query",
    "delete_corpus",
    "reset_all_corpora",
}


async def _run(command: str, args: list[str], cwd: str | None) -> dict[str, Any]:
    server = StdioServerParameters(command=command, args=args, cwd=cwd)
    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            response = await session.list_tools()

    tool_names = sorted(tool.name for tool in response.tools)
    missing = sorted(REQUIRED_TOOLS - set(tool_names))
    return {
        "command": command,
        "args": args,
        "tool_count": len(tool_names),
        "required_tools_present": not missing,
        "missing_required_tools": missing,
        "tools": tool_names,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--command",
        default="mapu",
        help="MCP server command to execute; defaults to installed mapu script.",
    )
    parser.add_argument(
        "--arg",
        action="append",
        default=None,
        dest="args",
        help="Argument to pass to command. Defaults to one 'mcp' argument.",
    )
    parser.add_argument("--cwd", default=None, help="Optional working directory for the server.")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    result = asyncio.run(_run(args.command, args.args or ["mcp"], args.cwd))
    if args.json_output:
        print(json.dumps(result, indent=2))
    else:
        print(f"MCP stdio smoke: {result['tool_count']} tools")
        print("Required tools present:", result["required_tools_present"])
        if result["missing_required_tools"]:
            print("Missing required tools:", ", ".join(result["missing_required_tools"]))

    output_path = Path("logs") / "mcp_stdio_smoke_last.json"
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    except OSError:
        pass

    if not result["required_tools_present"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
