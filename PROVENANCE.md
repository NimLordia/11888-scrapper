# Extraction provenance

The [Zer4You repository](https://github.com/NimLordia/zer4youscrap) contained code for two unrelated scrape targets. An [11888 repository](https://github.com/NimLordia/11888-scrapper) already existed with its own sequential scanner. This refactor places the consolidated phonebook implementation in that existing 11888 project and removes the need to maintain phonebook scripts in the flower-product repository.

The 11888-specific files were:

| Original file | Original responsibility | Replacement |
| --- | --- | --- |
| `autoscrap.py` in Zer4You | Backward scan from a known numeric ID, then forward collection | Explicit profiles or finite inclusive ID range in `phonebook/cli.py` |
| `phoneScrap.py` in Zer4You | Unbounded numeric block probing and collection | Same explicit profiles or bounded ID range |
| `scrapAll.py` in Zer4You | Probe almost 50 million numeric profile IDs | Same explicit profiles or bounded ID range |
| `autoscrap.py` in 11888 | Sequential numeric scan with rotating placeholder proxies | Bounded sequential scan that continues across gaps; optional single proxy |
| `sqliteToCSV.py` | Export all contacts after `fetchall()` | Read-only cursor-based export in `phonebook/core.py` |

The original scripts are preserved in their respective repositories' Git histories. This refactor consolidates their shared selectors and intended SQLite-to-CSV workflow. Sequential scanning across gaps is preserved; automatic range discovery, endless probing, and proxy rotation are removed. There is no backward compatibility with the legacy database schema. No real database or personal directory export was copied.

The retained selectors are `div.details`, `div.share_header div.name h1`, `div.location div.address`, and `div.phones a.tel-link`. They are tested against invented local HTML only. No live 11888 scrape was run during this refactor.

Zer4You product scraping and product datasets belong in the Zer4You project. They are not dependencies of this project. No license has been added; the repository owner should choose a license before inviting reuse.
