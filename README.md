# CouponJP MCP server

Let AI assistants answer "where near here can I use a tourist coupon in Japan?"

[CouponJP](https://couponjp.com/) is a free coupon site for foreign tourists shopping in Japan: Don Quijote, drugstores (Sugi, Tsuruha, Sundrug, Cosmos, Kokumin), electronics stores, department stores and duty-free shops, about 2,200 stores in all. There's no app, sign-up or coupon code: tourists show the coupon page on their phone at checkout, on top of tax-free shopping.

This [Model Context Protocol](https://modelcontextprotocol.io/) server is read-only and needs no API key. It reads CouponJP's public data files (`https://couponjp.com/coupon-api.json`, `data.json`, `stations.json`), cached for an hour.

## Tools

| Tool | What it answers |
|---|---|
| `find_coupon_stores` | Stores near a shopping area, city, train station or coordinates, nearest first, with discount, address, distance, coupon link and map link. Place names work in English, Japanese, Chinese and Korean ("Namba", "心斎橋", "难波", "도톤보리"). |
| `list_coupon_brands` | Every chain with a coupon: category, top discount, number of stores. |
| `brand_coupon` | One chain: discount by purchase amount or product type, validity, the store's tax refund fee. |
| `compare_shopping_cost` | The same purchase at every chain after the coupon and the tax refund fee ("is a drugstore or department store cheaper?"). |
| `tax_free_guide` | Japan's tax-free rules for tourists (refund system since November 1, 2026) with links to detailed guides. |

Every tool takes `language` (`en`, `zh-CN`, `zh-TW`, `ja`, `ko`, `th`, `vi`, `id`, `ms`, `fil`, `hi`, `fr`, `de`, `es`, `it`, `pt`, `ru`) for names, addresses and links.

## Install

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

Claude Desktop (`claude_desktop_config.json`), Cursor, Windsurf and other MCP clients:

```json
{
  "mcpServers": {
    "couponjp": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/couponjp/couponjp-mcp", "couponjp-mcp"]
    }
  }
}
```

Claude Code:

```bash
claude mcp add couponjp -- uvx --from git+https://github.com/couponjp/couponjp-mcp couponjp-mcp
```

## Example

> "I'm near Shinsaibashi. Where can I use a tourist coupon?"

The assistant calls `find_coupon_stores(place="Shinsaibashi")` and gets the nearest stores in the Namba / Shinsaibashi / Dotonbori area, each with its discount and coupon link.

## Notes

- Discounts and conditions are set by each store and can change. The coupon shown on couponjp.com is what counts.
- Distances are straight-line. Train station names and locations come from [Wikidata](https://www.wikidata.org/) (CC0).
- Links carry `utm_source=mcp` so CouponJP can see how many people the tool sends.
- Environment variables (optional): `COUPONJP_DATA_DIR` reads the data files from a local folder, `COUPONJP_TTL` sets the cache time in seconds, and `COUPONJP_UTM` changes the link tag.

## License

MIT. Operated by NNT Corporation (NNT株式会社), Japan. Contact: info@couponjp.com
