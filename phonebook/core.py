"""HTML parsing, URL validation, and SQLite/CSV storage (no network side effects)."""

from dataclasses import dataclass
from collections.abc import Iterable, Iterator
import csv
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit

from bs4 import BeautifulSoup


@dataclass(frozen=True)
class Contact:
    name: str
    location: str
    phones: tuple[str, ...]
    page_url: str

    @property
    def record_key(self) -> str:
        payload = json.dumps(
            [self.page_url, self.name, self.location, sorted(self.phones)],
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_profile_url(value: str) -> str:
    """Accept only explicit HTTPS 11888 white-pages profile URLs."""
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme != "https"
        or parsed.netloc.lower() not in {"11888.gr", "www.11888.gr"}
        or parsed.query
        or parsed.fragment
        or not re.fullmatch(r"/search/white_pages/[1-9][0-9]*/?", parsed.path)
    ):
        raise ValueError("Expected https://www.11888.gr/search/white_pages/<id>/")
    return f"https://www.11888.gr{parsed.path.rstrip('/')}/"


def normalize_profile_urls(values: Iterable[str], max_pages: int = 100) -> list[str]:
    if max_pages < 1:
        raise ValueError("max_pages must be positive")
    urls: list[str] = []
    seen: set[str] = set()
    for line_number, line in enumerate(values, 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            url = normalize_profile_url(line)
        except ValueError as exc:
            raise ValueError(f"Invalid profile URL at entry {line_number}: {exc}") from exc
        if url not in seen:
            seen.add(url)
            urls.append(url)
        if len(urls) > max_pages:
            raise ValueError(f"URL list exceeds the {max_pages}-page limit")
    if not urls:
        raise ValueError("No profile URLs were supplied")
    return urls


def read_profile_urls(path: Path, max_pages: int = 100) -> list[str]:
    with path.open(encoding="utf-8-sig") as source:
        return normalize_profile_urls(source, max_pages)


def profile_range(start_id: int, end_id: int, max_pages: int = 100) -> Iterator[str]:
    """Validate bounds immediately, then construct each URL only as it is consumed."""
    if max_pages < 1:
        raise ValueError("max_pages must be positive")
    if start_id < 1 or end_id < start_id:
        raise ValueError("IDs must satisfy 1 <= start-id <= end-id")
    if end_id - start_id + 1 > max_pages:
        raise ValueError(f"Inclusive ID range exceeds the {max_pages}-page limit")
    return (f"https://www.11888.gr/search/white_pages/{number}/" for number in range(start_id, end_id + 1))


def parse_contacts(html: str, page_url: str) -> list[Contact]:
    """Reuse the original selectors; containers without a name are ignored."""
    soup = BeautifulSoup(html, "html.parser")
    contacts: list[Contact] = []
    for details in soup.select("div.details"):
        name_element = details.select_one("div.share_header div.name h1")
        name = name_element.get_text(" ", strip=True) if name_element else ""
        if not name:
            continue
        address = details.select_one("div.location div.address")
        location = address.get_text(" ", strip=True) if address else ""
        phones = set()
        for link in details.select("div.phones a.tel-link"):
            href = link.get("href", "")
            if href.lower().startswith("tel:"):
                phone = href[4:].strip()
                if phone:
                    phones.add(phone)
        contacts.append(Contact(name, location, tuple(sorted(phones)), page_url))
    return contacts


def initialize_database(connection: sqlite3.Connection) -> None:
    validate_database_schema(connection, allow_missing=True)
    connection.execute(
        """CREATE TABLE IF NOT EXISTS contacts (
            record_key TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            location TEXT NOT NULL,
            phones TEXT NOT NULL,
            page_url TEXT NOT NULL
        )"""
    )
    connection.commit()


def validate_database_schema(connection: sqlite3.Connection, allow_missing: bool = False) -> None:
    columns = connection.execute("PRAGMA table_info(contacts)").fetchall()
    if not columns and allow_missing:
        return
    if (
        [column[1] for column in columns] != ["record_key", "name", "location", "phones", "page_url"]
        or columns[0][5] != 1
    ):
        raise ValueError(
            "Unsupported contacts schema. Use a new database path; legacy 11888_data.db "
            "files require a separate migration and are never modified automatically."
        )


def save_contacts(connection: sqlite3.Connection, contacts: list[Contact]) -> int:
    """Commit one page atomically; repeat imports of unchanged records add zero rows."""
    before = connection.total_changes
    with connection:
        connection.executemany(
            "INSERT OR IGNORE INTO contacts VALUES (?, ?, ?, ?, ?)",
            (
                (item.record_key, item.name, item.location,
                 json.dumps(sorted(item.phones), ensure_ascii=False), item.page_url)
                for item in contacts
            ),
        )
    return connection.total_changes - before


def spreadsheet_safe(value: str) -> str:
    """Keep contact fields from becoming formulas when a CSV is opened in a sheet."""
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def export_csv(database: Path, output: Path) -> int:
    """Read SQLite in read-only mode and stream records instead of using fetchall()."""
    if database.resolve() == output.resolve():
        raise ValueError("CSV output must be different from the database")
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        validate_database_schema(connection)
        cursor = connection.execute(
            "SELECT name, location, phones, page_url FROM contacts ORDER BY record_key"
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", newline="", encoding="utf-8-sig") as destination:
            writer = csv.writer(destination)
            writer.writerow(["name", "location", "phones", "page_url"])
            count = 0
            for name, location, phones, page_url in cursor:
                writer.writerow([
                    spreadsheet_safe(name), spreadsheet_safe(location),
                    spreadsheet_safe(", ".join(json.loads(phones))), spreadsheet_safe(page_url),
                ])
                count += 1
        return count
    finally:
        connection.close()
