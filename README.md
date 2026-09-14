# Greek phonebook scraper (11888)

A small Python project that parses 11888-style contact HTML, stores deduplicated records in SQLite, and streams them to CSV. This is the [11888 project](https://github.com/NimLordia/11888-scrapper), separate from the [Zer4You flower-product scraper](https://github.com/NimLordia/zer4youscrap).

**Status:** refactored prototype with an offline demonstration. Current live-site selector compatibility has not been verified. This is not a production crawler, and the demonstration does not establish that live collection works.

## Quick start: no website access

Requires Python 3.12 (the version used for local verification and CI).

```sh
git clone https://github.com/NimLordia/11888-scrapper.git
cd 11888-scrapper
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m phonebook scrape --demo --database data/demo.sqlite
python -m phonebook export --database data/demo.sqlite --output data/demo.csv
python -m unittest discover -s tests -v
```

The demo parses two obviously fictional entries from `phonebook/fixtures/demo.html`. It requires no Chrome installation, starts no browser, and makes no network requests. Repeating the demo adds zero duplicate rows. The displayed phone values are invalid test placeholders, not real telephone numbers. If `--database` is omitted, demo data uses `data/demo.sqlite` and live collection uses `data/contacts.sqlite`, keeping their defaults separate.

## Explicit profile collection

For a permitted live check, install Chrome and prepare a local `profiles.txt` containing only the exact profile URLs you intend to process, one per line. The accepted shape is `https://www.11888.gr/search/white_pages/<numeric-id>/`; replace the placeholder with an actual profile URL you are authorized to use. Blank lines and lines beginning with `#` are ignored.

```sh
python -m phonebook scrape --urls profiles.txt --database data/contacts.sqlite --max-pages 25 --delay 3
```

Alternatively, supply repeated `--url` arguments instead of a file. The list is validated before a browser starts. Duplicate URLs are canonicalized and visited once. The default limit is 100 URLs; `--max-pages` (alias `--max-urls`) explicitly sets a different positive limit. The tool does not discover URLs or follow links. Delay is at least two seconds between pages, with a three-second default. Selenium may download a driver on first use. Browser and database handles are closed on success, failure, or interruption.

## Finite sequential scans and gaps

The original project intentionally visits consecutive numeric IDs because an empty profile can be followed by a populated one. That behavior is retained with **explicit inclusive bounds** and no default scan range:

```sh
# Syntax only: choose bounds that you are permitted to inspect.
python -m phonebook scrape --start-id START_ID --end-id END_ID --database data/contacts.sqlite --max-pages 100
```

Both bounds must be positive integers, and the end must be at least the start. The range must fit the selected page limit before any browser starts. URLs are generated lazily, so a long explicitly configured finite range does not allocate a list of every URL. There is no endless scanning mode. Rerunning a range deduplicates unchanged records; there is no automatic checkpoint.

Missing content, redirects, and navigation/selector errors are logged as **unresolved** and the scan continues to the next requested ID or URL. A gap never signals the end of the range. The summary reports requested, parsed, unresolved, and newly inserted counts. A run with unresolved pages exits with status 1; a complete run exits 0, and interruption exits 130. This conservatively avoids claiming an empty profile was verified when it might instead be a consent page, timeout, or selector change. Database errors stop the run; already committed pages remain saved.

An optional `--proxy http://proxy.example:8080` configures one proxy for your network; the default is a direct connection. The old rotating placeholder proxy list was removed.

The live adapter waits for `div.details` and reuses the original name, address, and phone selectors. Selector presence alone does not prove a fully loaded or complete listing. Consent pages, rate limits, dynamic content, and site redesigns are not handled. Use only for permitted collection; review the site's current access rules before running it. Keep collected personal records and profile URL lists out of version control. No real directory records are included in the current source tree. The old database remains in the existing repository's Git history; this refactor does not rewrite history.

## Data and export

Each contact contains a name, location, sorted unique phone values, and source URL. Empty name containers are skipped; absent optional fields remain empty. A SHA-256 key over the normalized record fields makes unchanged records idempotent, including when phone order changes. A changed record is a new snapshot: this project does not resolve identities or update a person's existing record. SQLite writes are transactional per page.

The exporter reads this project's database schema in read-only mode and iterates its cursor, avoiding loading the entire table into memory. CSV uses UTF-8 with a BOM for spreadsheet compatibility. Fields that could be interpreted as spreadsheet formulas are prefixed with an apostrophe; the database retains their original values. Export overwrites the specified CSV path. Legacy databases require a separate migration and are not supported by this exporter.

## Project layout

```text
phonebook/core.py             Pure parsing, validation, SQLite persistence, CSV export
phonebook/cli.py              CLI and optional Selenium lifecycle
phonebook/fixtures/demo.html  Invented offline records
tests/test_phonebook.py       Offline tests; no website requests
PROVENANCE.md                Relationship to the original mixed repository
```

Imports do not start browsers or create files. Tests cover parsing, bounded URL/range validation, continuation across gaps, deduplication, CSV output, legacy-schema rejection, and browser cleanup on failure. There are no live-site integration results or benchmark claims.
