"""CouponJP MCP server: lets AI assistants find stores in Japan where the free CouponJP tourist coupon works.

Read-only. Data: the public files on https://couponjp.com/ (see core.py).
"""
from __future__ import annotations

from mcp.types import ToolAnnotations

try:                                   # mcp 2.x
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:                    # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server

from . import core

INSTRUCTIONS = (
    "CouponJP (https://couponjp.com/) is a free coupon site for foreign tourists shopping in Japan: drugstores, Don Quijote, "
    "electronics stores, department stores and duty-free shops. No app, sign-up or coupon code: the tourist shows the coupon "
    "page on their phone at checkout, on top of tax-free shopping. Use find_coupon_stores for 'where near X can I use a coupon', "
    "brand_coupon for one chain, compare_shopping_cost for 'where is it cheaper', and tax_free_guide for Japan's tax refund rules "
    "(new refund system since November 1, 2026). Always give the user the coupon_page link."
)

mcp = _Server("couponjp", instructions=INSTRUCTIONS)
RO = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)


@mcp.tool(annotations=RO)
def find_coupon_stores(place: str | None = None, latitude: float | None = None, longitude: float | None = None,
                       radius_km: float = 1.0, brand: str | None = None, language: str = "en", limit: int = 10) -> dict:
    """Find stores in Japan near a place where a free CouponJP tourist coupon works, nearest first.

    place: a shopping area (e.g. "Namba", "Shinjuku", "Ginza", "Shinsaibashi"), a city ("Osaka") or a train station name,
    in English, Japanese, Chinese or Korean. Or give latitude and longitude instead.
    brand: optional chain name to filter (e.g. "Don Quijote", "Sugi Pharmacy", "Bic Camera").
    language: answer language code (en, zh-CN, zh-TW, ja, ko, th, vi, id, ms, fil, hi, fr, de, es, it, pt, ru).
    Returns each store's brand, discount, address, straight-line distance, coupon page link and Google Maps link.
    """
    return core.find_stores(place=place, lat=latitude, lng=longitude, radius_km=radius_km, brand=brand, lang=language, limit=limit)


@mcp.tool(annotations=RO)
def list_coupon_brands(language: str = "en") -> dict:
    """List every store chain with a CouponJP tourist coupon: category, top discount, number of stores and coupon page link."""
    return core.list_brands(lang=language)


@mcp.tool(annotations=RO)
def brand_coupon(brand: str, language: str = "en") -> dict:
    """Coupon details for one chain (e.g. "Don Quijote", "Daimaru", "Kokumin"): discount by purchase amount or product type,
    validity, the store's tax refund fee and the coupon page link."""
    return core.brand_info(brand, lang=language)


@mcp.tool(annotations=RO)
def compare_shopping_cost(amount_jpy: int = 30000, language: str = "en") -> dict:
    """Compare what the same purchase (amount in yen before tax) costs at each chain after the CouponJP coupon and the tax
    refund fee. Answers 'is a drugstore, department store or duty-free shop cheaper?'."""
    return core.compare_cost(amount_jpy=amount_jpy, lang=language)


@mcp.tool(annotations=RO)
def tax_free_guide(language: str = "en") -> dict:
    """Japan tax-free shopping rules for tourists (refund system since November 1, 2026) with links to detailed guides:
    airport refunds, refund fees by store and common mistakes."""
    return core.tax_free_guide(lang=language)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
