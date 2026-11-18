#!/usr/bin/env python3
"""Normalize the original catalog export into catalog.json (products) and sku-aliases.json (aliases).

Reads only backup/catalog-original.json, so re-running it always produces the same output.
Exits with status 1 if any rule from docs/json-format.md is violated in the output.
Rules mirror the app's CatalogRules; comparison key = trim, collapse whitespace, uppercase.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKUP = ROOT / "backup" / "catalog-original.json"
PRODUCTS_OUT = ROOT / "catalog.json"
ALIASES_OUT = ROOT / "sku-aliases.json"
SCHEMA_VERSION = 1


def collapse(value: str) -> str:
    """Trim ends and collapse runs of whitespace (product values)."""
    return " ".join(value.split())


def key(value: str) -> str:
    """Comparison key used everywhere for matching (same as the app's Catalog.key)."""
    return " ".join(value.split()).upper()


def write_records(path: Path, envelope: dict, array_name: str, records: list) -> None:
    """Write the envelope with one record per line so git diffs stay readable."""
    lines = ["{"]
    for field, value in envelope.items():
        lines.append(f"  {json.dumps(field)}: {json.dumps(value, ensure_ascii=False)},")
    lines.append(f"  {json.dumps(array_name)}: [")
    for index, record in enumerate(records):
        comma = "," if index < len(records) - 1 else ""
        lines.append(f"    {json.dumps(record, ensure_ascii=False)}{comma}")
    lines.append("  ]")
    lines.append("}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    raw = json.loads(BACKUP.read_text(encoding="utf-8"))
    report: list[str] = []
    problems: list[str] = []

    # ---- Products -------------------------------------------------------
    products = []
    for row in raw["products"]:
        cleaned = {}
        for field, value in row.items():
            if field == "":
                continue  # unnamed column in the source sheet
            name = "Color" if field == "Color " else field.strip()
            cleaned[name] = collapse(value)
        if any(cleaned.values()):
            products.append(cleaned)
    report.append(f"Products with data: {len(products)}")

    no_sku = [p for p in products if not p["SKU"]]
    products = [p for p in products if p["SKU"]]
    report.append(f"Removed, no SKU: {[p['Name'] for p in no_sku]}")

    test_rows = [p for p in products if "test_" in (p["SKU"] + p["upc"] + p["Network"] + p["Name"]).lower()]
    products = [p for p in products if p not in test_rows]
    report.append(f"Removed, test placeholder: {[p['SKU'] for p in test_rows]}")

    by_sku = defaultdict(list)
    for p in products:
        by_sku[key(p["SKU"])].append(p)
    deleted_skus = set()
    kept: list[dict] = []
    for sku_key, rows in by_sku.items():
        if len(rows) == 1:
            kept.append(rows[0])
        elif all(r == rows[0] for r in rows):
            kept.append(rows[0])
            report.append(f"Duplicate SKU, identical rows, kept one: {sku_key}")
        else:
            deleted_skus.add(sku_key)
            report.append(f"Duplicate SKU, differing rows, deleted all: {sku_key} ({len(rows)} rows)")
    products = [p for p in kept if key(p["SKU"]) not in deleted_skus]

    by_upc = defaultdict(list)
    for p in products:
        if p["upc"]:
            by_upc[key(p["upc"])].append(p)
    cleared_upcs = set()
    for upc_key, rows in by_upc.items():
        if len({key(r["SKU"]) for r in rows}) > 1:
            cleared_upcs.add(upc_key)
            for r in rows:
                r["upc"] = ""
    report.append(f"UPCs cleared (shared by different SKUs): {sorted(cleared_upcs)}")

    # Direct SKU and UPC lookups, used to check that every way of resolving a value agrees.
    sku_index = {key(p["SKU"]): key(p["SKU"]) for p in products}
    upc_index = {key(p["upc"]): key(p["SKU"]) for p in products if p["upc"]}

    def resolve(value_key: str):
        return sku_index.get(value_key) or upc_index.get(value_key)

    # ---- Aliases --------------------------------------------------------
    aliases = []
    seen = set()
    for row in raw["aliases"]:
        lookup = row.get("Lookup", "").strip()
        returned = row.get("Return", "").strip()
        if not lookup or not returned or lookup.lower() == "lookupvalue":
            continue
        pair = (key(lookup), key(returned))
        if pair in seen:
            continue
        seen.add(pair)
        aliases.append({"Lookup": lookup, "Return": returned})
    report.append(f"Aliases after removing blanks/duplicates: {len(aliases)}")

    returns_by_lookup = defaultdict(set)
    for a in aliases:
        returns_by_lookup[key(a["Lookup"])].add(key(a["Return"]))
    conflicting = {k for k, v in returns_by_lookup.items() if len(v) > 1}
    report.append(f"Lookups mapping to more than one Return (all pairs removed): {sorted(conflicting)}")
    gone = deleted_skus | cleared_upcs
    before = len(aliases)
    aliases = [a for a in aliases if key(a["Lookup"]) not in conflicting]
    aliases = [a for a in aliases if key(a["Return"]) not in gone]
    report.append(f"Removed, pointing at deleted SKU or cleared UPC: {before - len(aliases)} (incl. conflicting lookups above)")

    disagreeing = []
    for a in aliases:
        lookup_product = resolve(key(a["Lookup"]))
        return_product = resolve(key(a["Return"]))
        if lookup_product and return_product and lookup_product != return_product:
            disagreeing.append(a)
    aliases = [a for a in aliases if a not in disagreeing]
    report.append(f"Removed, agreement conflict: {[(a['Lookup'], a['Return']) for a in disagreeing]}")

    # ---- Invariants (script fails if any is violated) -------------------
    if len({key(p["SKU"]) for p in products}) != len(products):
        problems.append("SKU is not unique")
    upcs = [key(p["upc"]) for p in products if p["upc"]]
    if len(upcs) != len(set(upcs)):
        problems.append("UPC shared by more than one product")
    for p in products:
        if p["upc"] and sku_index.get(key(p["upc"]), key(p["SKU"])) != key(p["SKU"]):
            problems.append(f"UPC {p['upc']} equals another product's SKU")
        if p["upc"] and key(p["upc"]) == key(p["SKU"]):
            report.append(f"Note: UPC equals its own SKU (allowed): {p['SKU']}")
    lookups = defaultdict(set)
    for a in aliases:
        lookups[key(a["Lookup"])].add(key(a["Return"]))
    if any(len(v) > 1 for v in lookups.values()):
        problems.append("Lookup maps to more than one Return")
    for a in aliases:
        lp, rp = resolve(key(a["Lookup"])), resolve(key(a["Return"]))
        if lp and rp and lp != rp:
            problems.append(f"Agreement violated: {a}")
    unlinked = [a for a in aliases if not resolve(key(a["Return"]))]
    report.append(f"Unlinked aliases (Return matches no product yet, kept): {len(unlinked)}")

    if problems:
        print("\n".join(report))
        print("INVARIANT FAILURES:", *problems, sep="\n  ")
        return 1

    write_records(
        PRODUCTS_OUT,
        {"schemaVersion": SCHEMA_VERSION, "kind": "catalog"},
        "products",
        products,
    )
    write_records(
        ALIASES_OUT,
        {"schemaVersion": SCHEMA_VERSION, "kind": "aliases"},
        "aliases",
        aliases,
    )
    print("\n".join(report))
    print(f"\nWrote {PRODUCTS_OUT.name}: {len(products)} products")
    print(f"Wrote {ALIASES_OUT.name}: {len(aliases)} aliases")
    print("All invariants OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
