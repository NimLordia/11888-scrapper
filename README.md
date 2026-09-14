# 11888 Greek Phone Book Scraper

A Python automation project that collects directory records from **11888.gr**, saves them to SQLite, and exports them to CSV. Built for a long-running, one-time scan of the directory's numeric URLs.

**Stack:** Python · Selenium · Chrome WebDriver · SQLite · CSV

## Why scan URLs one by one?

The scraper visits URLs with this structure:

```text
https://www.11888.gr/search/white_pages/{number}/
```

The numeric URL space is sparse: some numbers return records and others return no data. There is no known list of populated numbers available to this scraper, so it checks each number in sequence.

**An empty URL is a gap, not the end of the scan.** The scraper logs the empty result and continues to the next number. This is intentional: stopping after an empty page could miss records at later numbers.

## How it works

1. Selects a configured proxy and opens a headless Chrome session.
2. Visits the next numeric URL and looks for directory records.
3. Extracts each record's name, address, and phone numbers, together with the source URL and scanned number.
4. Inserts each record into SQLite and commits it immediately.
5. Closes the browser and advances to the next number, including when no records were found.

When multiple distinct proxies are configured, the script avoids using the same proxy on consecutive URLs. CSV export runs separately, allowing collection and export to happen at different times.

## Setup

You need Python 3, Google Chrome, and a working Chrome WebDriver setup.

```bash
git clone https://github.com/NimLordia/11888-scrapper.git
cd 11888-scrapper
python -m venv .venv
```

Activate the virtual environment:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# macOS / Linux
source .venv/bin/activate
```

Install the dependencies:

```bash
python -m pip install -r requirements.txt
```

If ChromeDriver cannot be located, set its executable path in the `Service(...)` configuration in `autoscrap.py`.

## Configure the scan

Edit these settings in `autoscrap.py` before running it:

| Setting | Purpose |
| --- | --- |
| `proxies` | Replace the example proxy addresses with working proxies. Use distinct entries when configuring multiple proxies. |
| `scrape_page = 1` | The first numeric URL to check. Change this to start at a different number or manually continue an interrupted scan. |
| `while scrape_page < 50000000:` | The exclusive upper bound. The default checks numbers 1 through 49,999,999. |

For a direct connection without a proxy, set:

```python
proxies = [None]
```

Keep the list nonempty: the script selects an entry on every iteration.

For an unbounded scan, replace the loop condition with `while True:`. Empty results do not stop either version; the default version stops at its configured upper bound.

## Run

Run commands from the repository directory so both scripts use the same database path.

```bash
python autoscrap.py
```

The console reports each number being checked, whether records were found, and the records inserted. Data is written to `11888_data.db` as the scan progresses. Press `Ctrl+C` to interrupt the run; records already committed remain in the database.

The repository includes an existing `11888_data.db`. To start with an empty dataset, move that file elsewhere before running the scraper; the script creates the database and table if they do not exist.

## Export to CSV

```bash
python sqliteToCSV.py
```

This reads the `contacts` table in `11888_data.db` and writes all stored records, including column headers, to a UTF-8 `contacts.csv`. Each export replaces any existing CSV at that path.

### Record fields

| Column | Contents |
| --- | --- |
| `id` | Auto-generated database record ID |
| `name` | Name extracted from the directory record |
| `location` | Address extracted from the record |
| `phones` | Phone numbers extracted from `tel:` links, joined with commas |
| `page_url` | Browser URL when the record was extracted, including any redirect |
| `page` | Numeric URL value checked by the scraper |

Failed name or address extraction and missing phone numbers are recorded as `N/A`.

## Running and restarting

- The intended workflow is one continuous pass. There is no automatic checkpoint or deduplication; revisiting populated URLs appends records again.
- To continue after an interruption, inspect the last console output and set `scrape_page` to the number you want to retry or continue from. An interrupted URL may already have some records saved.
- Browser or navigation errors can end the run. The script currently uses a fixed 0.2-second pause after navigation and has no automatic retry, so slow-loading content can be missed.
- The CSV exporter loads the full table into memory before writing. Large datasets may require adapting it to stream rows.

## Project files

```text
autoscrap.py       Sequential URL scan, extraction, and SQLite storage
sqliteToCSV.py     SQLite-to-CSV export
requirements.txt  Pinned Python dependencies
11888_data.db     Included SQLite database; subsequent runs append records
```
