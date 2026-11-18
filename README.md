# Inventory Catalog

Normalized product and alias data for the Inventory Scanning App.

## Files

- `catalog.json`: products (`kind: "catalog"`).
- `sku-aliases.json`: aliases (`kind: "aliases"`).
- `docs/json-format.md`: the import format and the rules.
- `backup/catalog-original.json`: the original export, unchanged. Used as the source for normalization.
- `tools/normalize.py`: regenerates the two files from the backup and checks every rule.

## Updating the data

1. Make the change in `catalog.json` or `sku-aliases.json` (or edit the backup and regenerate).
2. Run `python3 tools/normalize.py`. It exits with an error if any rule is violated.
3. Commit and push. GitHub Pages serves the files at:
   - https://swhit237.github.io/inventory-catalog/catalog.json
   - https://swhit237.github.io/inventory-catalog/sku-aliases.json

## Publishing

In the repository's Settings → Pages, set the source to the `main` branch, root folder. Files are served about a minute after a push. The app checks these URLs with standard HTTP conditional requests, so the files do not need a manifest.
