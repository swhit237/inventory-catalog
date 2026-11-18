# Catalog JSON format

Every file is a single JSON object with a `schemaVersion` and a `kind`.

```json
{
  "schemaVersion": 1,
  "kind": "catalog",
  "products": [
    { "SKU": "MC6V4LL/A", "Name": "13-inch MacBook Air (M4) 512GB Sky Blue", "upc": "195949000000", "Manufacturer": "Apple" }
  ],
  "aliases": [
    { "Lookup": "MC6V4 LL/A", "Return": "MC6V4LL/A" }
  ]
}
```

## Envelope

| Field | Rule |
|---|---|
| `schemaVersion` | Required. Must be `1`. |
| `kind` | Required. `"catalog"` or `"aliases"`. |
| `products` | Array. Allowed only when `kind` is `"catalog"`. |
| `aliases` | Array. Allowed in both kinds. |

- `kind: "catalog"` may contain `products`, `aliases`, or both (at least one array is required). Products are evaluated together with aliases, so an alias can point at a product in the same file.
- `kind: "aliases"` must contain `aliases` and must not contain `products`.
- Unknown keys are ignored.
- Limits: 10 MB per file, 50,000 records per array.

The repo ships `catalog.json` (`kind: "catalog"`, products only) and `sku-aliases.json` (`kind: "aliases"`).

## Product fields

| Field | Required | Rule |
|---|---|---|
| `SKU` | yes | Non-empty after trimming ends. |
| `Name` | yes | Non-empty after trimming ends. |
| `upc` | no | Digits only, 8–14 characters, or empty. |
| `Manufacturer`, `productfamily`, `productfamilybrand`, `Model`, `Capacity`, `Color`, `Variant`, `Network`, `searchterm` | no | Strings. May be empty or missing. |

## Alias fields

| Field | Required | Rule |
|---|---|---|
| `Lookup` | yes | Non-empty after trimming ends. Whitespace between characters is kept, so `MLXTY LL/A` is different text from `MLXTYLL/A`. |
| `Return` | yes | A **direct SKU or UPC** of a product. It is never looked up through another alias, so alias chains are not followed. If it matches no product yet, the alias is accepted and shown as "unlinked". |

## Matching and comparison

Comparisons ignore case and treat any run of whitespace as one space, after trimming ends. The stored text is not changed by this; only the comparison is.

## The four rules

1. **SKU is unique.** A SKU belongs to one product.
2. **UPC is unique.** A UPC belongs to one product, and a UPC may not equal another product's SKU.
3. **Lookup maps to one Return.** A Lookup can have many Returns across records, but only one distinct Return. A record can have many Lookups.
4. **Agreement.** Every way a value can resolve must reach the same product: as a direct SKU, as a direct UPC, or as an alias `Lookup` whose `Return` is a direct SKU or UPC. Example violation: UPC `X` belongs to product A, but an alias with `Lookup` `X` returns product B.

Rule 4 is also checked when a product is added, because a new product can activate unlinked aliases whose `Return` is its SKU or UPC.

## What gets rejected

**The whole file is rejected** (nothing is imported; one clear reason is shown):
- Not valid JSON, or the envelope is wrong (missing `schemaVersion` or `kind`).
- `schemaVersion` is not supported.
- `kind` does not match the source type, or the file contains a `products` array for an aliases source.
- No `products` or `aliases` array at all.
- Over the size or record limits.

**One row is rejected** (the rest of the file still imports):
- A value that is not a string, or a missing required field.
- A UPC with the wrong format.
- Any rule violation above.

A row that takes part in any conflict is rejected, including both rows of a two-row conflict. Rows that already exist in the catalog are counted as "already present" and are neither accepted nor rejected. The result does not depend on row order.

## Example reports

- A file with 99 good rows and one conflicting row: **99 accepted, 1 rejected**. The preview and the import show the same numbers.
- A file with an unsupported `schemaVersion`: **rejected**, 0 rows imported.
