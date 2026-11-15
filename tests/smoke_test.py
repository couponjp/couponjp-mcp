"""Start the server over stdio like an MCP client would, list the tools and call each one.
Run: COUPONJP_DATA_DIR=.testdata python tests/smoke_test.py   (omit the variable to use the live couponjp.com files)"""
import asyncio
import json
import os
import sys

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def main() -> int:
    params = StdioServerParameters(command=sys.executable, args=["-m", "couponjp_mcp.server"], env=dict(os.environ))
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            init = await s.initialize()
            info = getattr(init, "server_info", None) or getattr(init, "serverInfo")
            print("server:", info.name, "| instructions:", (init.instructions or "")[:60], "…")
            tools = await s.list_tools()
            print("tools:", [t.name for t in tools.tools])
            calls = [("find_coupon_stores", {"place": "心斎橋", "language": "zh-TW", "limit": 2}),
                     ("find_coupon_stores", {"latitude": 35.6984, "longitude": 139.7731, "radius_km": 0.6, "limit": 2}),
                     ("list_coupon_brands", {"language": "th"}),
                     ("brand_coupon", {"brand": "Donki"}),
                     ("compare_shopping_cost", {"amount_jpy": 30000}),
                     ("tax_free_guide", {"language": "ko"}),
                     ("find_coupon_stores", {"place": "nowhere-xyz"})]
            bad = 0
            for name, args in calls:
                res = await s.call_tool(name, args)
                sc = getattr(res, "structured_content", None) if hasattr(res, "structured_content") else getattr(res, "structuredContent", None)
                ok = not (getattr(res, "is_error", None) if hasattr(res, "is_error") else getattr(res, "isError", False))
                try:
                    data = sc or json.loads(res.content[0].text)
                except (ValueError, IndexError):
                    data = res.content[0].text if res.content else None
                bad += not ok
                print(f"\n{name} {args} -> {'ok' if ok else 'ERROR'}\n  " + json.dumps(data, ensure_ascii=False)[:420])
            return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
