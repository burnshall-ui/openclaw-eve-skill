#!/usr/bin/env python3
"""EVE ESI API query helper.

Usage (generic endpoint mode):
    python esi_query.py --token <ACCESS_TOKEN> --endpoint /characters/12345/wallet/
    python esi_query.py --token <ACCESS_TOKEN> --endpoint /characters/12345/assets/ --pages
    python esi_query.py --token <ACCESS_TOKEN> --endpoint /characters/12345/contacts/ --method POST --body '[{"contact_id":123,"standing":10}]'

Usage (high-level PI/market actions):
    python esi_query.py --action pi_planets --token <ACCESS_TOKEN> --character-id 12345 --pretty
    python esi_query.py --action pi_planet_detail --token <ACCESS_TOKEN> --character-id 12345 --planet-id 98765 --pretty
    python esi_query.py --action pi_status --token <ACCESS_TOKEN> --character-id 12345 --pretty
    python esi_query.py --action market_price_bulk --pretty
    python esi_query.py --action jita_price --type-id 2393 --pretty

Requires: Python 3.8+ (uses only stdlib)
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

BASE_URL = "https://esi.evetech.net/latest"
USER_AGENT = "OpenClaw-ESI-Skill/1.0 (https://github.com/openclaw/openclaw)"
JITA_REGION_ID = 10000002

# Base PI product mapping (P0 + P1 complete, selected P2-P4 common outputs).
PI_PRODUCTS: dict[int, str] = {
    # P0 (core set)
    2393: "Aqueous Liquids",
    2396: "Base Metals",
    2397: "Carbon Compounds",
    2398: "Complex Organisms",
    2401: "Heavy Metals",
    # P1 (core set)
    2389: "Bacteria",
    2390: "Biofuels",
    2399: "Industrial Fibers",
    3779: "Biomass",
    2400: "Precious Metals",
    2317: "Water",
    9828: "Silicon",
    # P2/P3/P4 (selected)
    44: "Enriched Uranium",
    3689: "Mechanical Parts",
    9836: "Consumer Electronics",
    9832: "Construction Blocks",
    3683: "Coolant",
    2867: "Broadcast Node",
    2868: "Camera Drones",
    2869: "Synthetic Synapses",
    2870: "Gel-Matrix Biopaste",
    2871: "Hazmat Detection Systems",
    2872: "Integrity Response Drones",
    2873: "Organic Mortar Applicators",
    2874: "Nano-Factory",
    2875: "Sterile Conduits",
}

# Approximate per-pin capacities for common PI storage structures.
# These values are used only for quick "needs attention" heuristics.
PI_STORAGE_CAPACITY_UNITS: dict[int, int] = {
    2524: 10000,  # common launchpad type in many setups
    2544: 10000,  # launchpad
    2256: 12000,  # storage facility (legacy type id in some fits)
}


def normalize_endpoint(endpoint: str) -> str:
    """Ensure endpoint starts with a leading slash."""
    if endpoint.startswith("/"):
        return endpoint
    return "/" + endpoint


def parse_utc_timestamp(value: str | None) -> datetime | None:
    """Parse an ESI timestamp in RFC3339 format."""
    if not value:
        return None
    try:
        fixed = value.replace("Z", "+00:00")
        return datetime.fromisoformat(fixed).astimezone(timezone.utc)
    except ValueError:
        return None


def resolve_pi_product_name(type_id: int | None) -> str:
    """Map PI type_id to readable product name."""
    if type_id is None:
        return "unknown"
    return PI_PRODUCTS.get(type_id, f"type_id:{type_id}")


def build_url(endpoint: str, page: int | None = None, params: dict[str, Any] | None = None) -> str:
    """Build endpoint URL with optional query params and pagination."""
    url = f"{BASE_URL}{normalize_endpoint(endpoint)}"
    query: dict[str, Any] = {}
    if params:
        query.update(params)
    if page is not None:
        query["page"] = page
    if query:
        sep = "&" if "?" in url else "?"
        url += sep + urllib.parse.urlencode(query)
    return url


def esi_request(
    endpoint: str,
    token: str | None = None,
    method: str = "GET",
    body: str | None = None,
    page: int | None = None,
    params: dict[str, Any] | None = None,
    allow_404: bool = False,
) -> tuple[dict | list | str | None, dict]:
    """Make a single ESI request. Returns (parsed_body, headers)."""
    url = build_url(endpoint, page=page, params=params)

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = body.encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req) as resp:
            resp_headers = {k.lower(): v for k, v in resp.getheaders()}
            raw = resp.read().decode("utf-8")
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = raw
            return parsed, resp_headers
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        remain = e.headers.get("X-ESI-Error-Limit-Remain", "?")
        reset = e.headers.get("X-ESI-Error-Limit-Reset", "?")
        print(f"HTTP {e.code}: {error_body}", file=sys.stderr)
        print(f"Error limit remaining: {remain}, resets in: {reset}s", file=sys.stderr)
        if e.code == 420:
            wait = int(reset) if reset.isdigit() else 60
            print(f"Rate limited. Waiting {wait}s...", file=sys.stderr)
            time.sleep(wait)
            return esi_request(
                endpoint=endpoint,
                token=token,
                method=method,
                body=body,
                page=page,
                params=params,
                allow_404=allow_404,
            )
        if allow_404 and e.code == 404:
            return None, {k.lower(): v for k, v in e.headers.items()}
        sys.exit(1)


def esi_request_all_pages(
    endpoint: str,
    token: str | None = None,
    params: dict[str, Any] | None = None,
) -> list:
    """Fetch all pages of a paginated GET endpoint."""
    first_page, headers = esi_request(endpoint, token=token, page=1, params=params)
    total_pages = int(headers.get("x-pages", "1"))
    if not isinstance(first_page, list):
        if first_page is None:
            return []
        return [first_page]

    all_results = list(first_page)
    for p in range(2, total_pages + 1):
        page_data, _ = esi_request(endpoint, token=token, page=p, params=params)
        if isinstance(page_data, list):
            all_results.extend(page_data)
            page_count = len(page_data)
        elif page_data is None:
            page_count = 0
        else:
            page_count = 1
        print(f"  Page {p}/{total_pages} fetched ({page_count} items)", file=sys.stderr)
    return all_results


def get_pi_planets(character_id: int, token: str) -> list:
    """Return all PI planets for a character."""
    endpoint = f"/characters/{character_id}/planets/"
    return esi_request_all_pages(endpoint, token=token)


def get_pi_planet_detail(character_id: int, planet_id: int, token: str) -> dict:
    """Return full PI colony detail: pins, links and routes."""
    endpoint = f"/characters/{character_id}/planets/{planet_id}/"
    result, _ = esi_request(endpoint, token=token, method="GET")
    if isinstance(result, dict):
        return result
    return {}


def get_universe_planet(planet_id: int) -> dict:
    """Return public planet metadata (name/system/type)."""
    endpoint = f"/universe/planets/{planet_id}/"
    result, _ = esi_request(endpoint, token=None, allow_404=True)
    if isinstance(result, dict):
        return result
    return {}


def get_market_price_bulk() -> list:
    """Fetch bulk adjusted/average prices for all item types."""
    result, _ = esi_request("/markets/prices/", token=None, method="GET")
    if isinstance(result, list):
        return result
    return []


def get_jita_price(type_id: int) -> dict:
    """Fetch current Jita buy/sell snapshot for one type."""
    sell_orders = esi_request_all_pages(
        endpoint=f"/markets/{JITA_REGION_ID}/orders/",
        token=None,
        params={"type_id": type_id, "order_type": "sell"},
    )
    buy_orders = esi_request_all_pages(
        endpoint=f"/markets/{JITA_REGION_ID}/orders/",
        token=None,
        params={"type_id": type_id, "order_type": "buy"},
    )

    sell_prices = [
        o.get("price")
        for o in sell_orders
        if isinstance(o, dict) and isinstance(o.get("price"), (int, float))
    ]
    buy_prices = [
        o.get("price")
        for o in buy_orders
        if isinstance(o, dict) and isinstance(o.get("price"), (int, float))
    ]

    lowest_sell = min(sell_prices) if sell_prices else None
    highest_buy = max(buy_prices) if buy_prices else None
    spread = None
    if lowest_sell is not None and highest_buy is not None:
        spread = round(lowest_sell - highest_buy, 2)

    return {
        "type_id": type_id,
        "region_id": JITA_REGION_ID,
        "lowest_sell": lowest_sell,
        "highest_buy": highest_buy,
        "spread": spread,
        "sell_order_count": len(sell_orders),
        "buy_order_count": len(buy_orders),
    }


def estimate_storage_fill_pct(pins: list[dict]) -> float | None:
    """Estimate max storage fill percentage across known storage pin types."""
    max_fill = None
    for pin in pins:
        if not isinstance(pin, dict):
            continue
        pin_type_id = pin.get("type_id")
        capacity = PI_STORAGE_CAPACITY_UNITS.get(pin_type_id)
        if not capacity:
            continue
        contents = pin.get("contents") or []
        if not isinstance(contents, list):
            continue
        total_amount = 0.0
        for item in contents:
            if not isinstance(item, dict):
                continue
            amount = item.get("amount")
            if isinstance(amount, (int, float)):
                total_amount += float(amount)
        fill = min(100.0, round((total_amount / float(capacity)) * 100.0, 2))
        if max_fill is None or fill > max_fill:
            max_fill = fill
    return max_fill


def parse_pi_status(planets_data: list, planet_details: dict | list) -> list[dict]:
    """Parse raw PI ESI responses into actionable per-planet status."""
    details_map: dict[str, dict] = {}
    if isinstance(planet_details, dict):
        details_map = {str(k): v for k, v in planet_details.items() if isinstance(v, dict)}
    elif isinstance(planet_details, list):
        for item in planet_details:
            if not isinstance(item, dict):
                continue
            planet_id = item.get("planet_id")
            detail = item.get("detail") if isinstance(item.get("detail"), dict) else item
            if planet_id is not None and isinstance(detail, dict):
                details_map[str(planet_id)] = detail

    now = datetime.now(timezone.utc)
    parsed: list[dict] = []

    for planet in planets_data:
        if not isinstance(planet, dict):
            continue

        planet_id = planet.get("planet_id")
        detail = details_map.get(str(planet_id), {})
        pins = detail.get("pins", []) if isinstance(detail, dict) else []
        routes = detail.get("routes", []) if isinstance(detail, dict) else []

        extractors: list[dict] = []
        attention_reasons: list[str] = []

        for pin in pins:
            if not isinstance(pin, dict):
                continue
            extractor = pin.get("extractor_details")
            if not isinstance(extractor, dict):
                continue

            product_type_id = extractor.get("product_type_id")
            expiry = pin.get("expiry_time")
            expiry_dt = parse_utc_timestamp(expiry)
            hours_remaining = None
            status = "idle"
            if expiry_dt is not None:
                hours_remaining = round((expiry_dt - now).total_seconds() / 3600.0, 2)
                status = "running" if hours_remaining > 0 else "expired"

            extractors.append({
                "product": resolve_pi_product_name(product_type_id),
                "product_type_id": product_type_id,
                "expiry": expiry,
                "hours_remaining": hours_remaining,
                "status": status,
            })

            if status == "expired":
                attention_reasons.append("Extractor already expired")
            elif hours_remaining is not None and hours_remaining <= 6:
                attention_reasons.append(f"Extractor expires in {hours_remaining}h")

        incoming_by_pin: dict[int, list[int]] = {}
        outgoing_by_pin: dict[int, list[int]] = {}
        for route in routes:
            if not isinstance(route, dict):
                continue
            source_pin = route.get("source_pin_id")
            destination_pin = route.get("destination_pin_id")
            content_type = route.get("content_type_id")
            if isinstance(source_pin, int) and isinstance(content_type, int):
                outgoing_by_pin.setdefault(source_pin, []).append(content_type)
            if isinstance(destination_pin, int) and isinstance(content_type, int):
                incoming_by_pin.setdefault(destination_pin, []).append(content_type)

        factories: list[dict] = []
        for pin in pins:
            if not isinstance(pin, dict):
                continue
            if "factory_details" not in pin and "schematic_id" not in pin:
                continue
            pin_id = pin.get("pin_id")
            if not isinstance(pin_id, int):
                continue
            input_types = sorted(set(incoming_by_pin.get(pin_id, [])))
            output_types = sorted(set(outgoing_by_pin.get(pin_id, [])))
            schematic = pin.get("schematic_id")
            factories.append({
                "input": ", ".join(resolve_pi_product_name(tid) for tid in input_types) if input_types else "unknown",
                "output": ", ".join(resolve_pi_product_name(tid) for tid in output_types) if output_types else "unknown",
                "schematic": f"Schematic {schematic}" if schematic is not None else "unknown",
            })

        storage_fill_pct = estimate_storage_fill_pct(pins)
        if storage_fill_pct is not None and storage_fill_pct >= 80:
            attention_reasons.append(f"Storage/Launchpad at {storage_fill_pct}%")

        unique_reasons = list(dict.fromkeys(attention_reasons))
        parsed.append({
            "planet_id": planet_id,
            "planet_name": detail.get("_planet_name", f"Planet {planet_id}"),
            "planet_type": planet.get("planet_type"),
            "solar_system_id": planet.get("solar_system_id"),
            "character": detail.get("_character_name", "unknown"),
            "extractors": extractors,
            "storage_fill_pct": storage_fill_pct,
            "factories": factories,
            "needs_attention": bool(unique_reasons),
            "action_required": "; ".join(unique_reasons) if unique_reasons else "none",
        })

    return parsed


def get_pi_status(character_id: int, token: str) -> list[dict]:
    """Fetch planets + details and return parsed, actionable PI status."""
    planets = get_pi_planets(character_id=character_id, token=token)
    details: dict[str, dict] = {}

    for planet in planets:
        if not isinstance(planet, dict):
            continue
        planet_id = planet.get("planet_id")
        if not isinstance(planet_id, int):
            continue

        detail = get_pi_planet_detail(character_id=character_id, planet_id=planet_id, token=token)
        planet_meta = get_universe_planet(planet_id)
        if planet_meta.get("name"):
            detail["_planet_name"] = planet_meta["name"]
        details[str(planet_id)] = detail

    return parse_pi_status(planets_data=planets, planet_details=details)


def run_action(args: argparse.Namespace, parser: argparse.ArgumentParser) -> Any:
    """Execute high-level action mode."""
    if args.action in {"pi_planets", "pi_planet_detail", "pi_status"}:
        if not args.token:
            parser.error(f"--token is required for action '{args.action}'")
        if args.character_id is None:
            parser.error(f"--character-id is required for action '{args.action}'")

    if args.action == "pi_planets":
        return get_pi_planets(character_id=args.character_id, token=args.token)

    if args.action == "pi_planet_detail":
        if args.planet_id is None:
            parser.error("--planet-id is required for action 'pi_planet_detail'")
        return get_pi_planet_detail(
            character_id=args.character_id,
            planet_id=args.planet_id,
            token=args.token,
        )

    if args.action == "pi_status":
        return get_pi_status(character_id=args.character_id, token=args.token)

    if args.action == "market_price_bulk":
        return get_market_price_bulk()

    if args.action == "jita_price":
        if args.type_id is None:
            parser.error("--type-id is required for action 'jita_price'")
        return get_jita_price(type_id=args.type_id)

    parser.error(f"Unsupported action: {args.action}")
    return None


def main():
    parser = argparse.ArgumentParser(description="Query EVE ESI API endpoints")
    parser.add_argument("--token", required=False, help="ESI access token (Bearer)")
    parser.add_argument("--endpoint", required=False,
                        help="ESI endpoint path, e.g. /characters/12345/wallet/")
    parser.add_argument("--method", default="GET", choices=["GET", "POST", "PUT", "DELETE"],
                        help="HTTP method (default: GET)")
    parser.add_argument("--body", default=None, help="JSON body for POST/PUT requests")
    parser.add_argument("--pages", action="store_true",
                        help="Automatically fetch all pages (GET only)")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")

    parser.add_argument(
        "--action",
        choices=["pi_planets", "pi_planet_detail", "pi_status", "market_price_bulk", "jita_price"],
        help="Run a high-level helper action instead of raw endpoint mode",
    )
    parser.add_argument("--character-id", type=int, help="EVE character ID for PI actions")
    parser.add_argument("--planet-id", type=int, help="Planet ID for pi_planet_detail")
    parser.add_argument("--type-id", type=int, help="Type ID for jita_price")
    args = parser.parse_args()

    if args.action:
        result = run_action(args, parser)
    else:
        if not args.endpoint:
            parser.error("--endpoint is required when --action is not used")
        endpoint = normalize_endpoint(args.endpoint)
        if args.pages and args.method == "GET":
            result = esi_request_all_pages(endpoint, token=args.token)
        else:
            result, headers = esi_request(endpoint, token=args.token, method=args.method, body=args.body)
            expires = headers.get("expires", "unknown")
            print(f"Cache expires: {expires}", file=sys.stderr)

    indent = 2 if args.pretty else None
    if isinstance(result, (dict, list)):
        print(json.dumps(result, indent=indent, ensure_ascii=False))
    else:
        print(result)


if __name__ == "__main__":
    main()
