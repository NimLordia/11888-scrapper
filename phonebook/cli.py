"""Small CLI; browser and database resources are created only when requested."""

import argparse
import math
from pathlib import Path
import sqlite3
import sys
import time

from .core import (
    export_csv, initialize_database, normalize_profile_url, normalize_profile_urls,
    parse_contacts, profile_range, read_profile_urls, save_contacts,
)


DEMO_URL = "https://example.invalid/fictional-phonebook/demo/"


def create_driver(timeout: float, proxy: str | None = None):
    from selenium import webdriver

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    if proxy:
        options.add_argument(f"--proxy-server={proxy}")
    driver = webdriver.Chrome(options=options)
    try:
        driver.set_page_load_timeout(timeout)
    except BaseException:
        driver.quit()
        raise
    return driver


def resolve_urls(args: argparse.Namespace):
    if args.max_pages < 1:
        raise ValueError("max-pages must be positive")
    if args.start_id is not None:
        if args.end_id is None:
            raise ValueError("--start-id requires --end-id")
        return profile_range(args.start_id, args.end_id, args.max_pages), args.end_id - args.start_id + 1
    if args.end_id is not None:
        raise ValueError("--end-id requires --start-id")
    if args.demo:
        return [], 0
    urls = (normalize_profile_urls(args.url, args.max_pages) if args.url
            else read_profile_urls(args.urls, args.max_pages))
    return urls, len(urls)


def scrape(args: argparse.Namespace) -> int:
    if not math.isfinite(args.delay) or args.delay < 2:
        raise ValueError("delay must be at least 2 seconds")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        raise ValueError("timeout must be positive")
    # Validate explicit URL lists or numeric bounds before opening a database/browser.
    urls, total_pages = resolve_urls(args)
    database = args.database or Path("data/demo.sqlite" if args.demo else "data/contacts.sqlite")
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    driver = None
    try:
        initialize_database(connection)
        if args.demo:
            html = (Path(__file__).parent / "fixtures" / "demo.html").read_text(encoding="utf-8")
            contacts = parse_contacts(html, DEMO_URL)
            inserted = save_contacts(connection, contacts)
            print(f"Offline demo: parsed {len(contacts)} fictional records; inserted {inserted}.")
            return 0

        from selenium.common.exceptions import TimeoutException, WebDriverException
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait

        driver = create_driver(args.timeout, args.proxy)
        inserted = 0
        parsed_pages = 0
        unresolved_pages = 0
        for index, url in enumerate(urls):
            if index:
                time.sleep(args.delay)
            try:
                driver.get(url)
                # Redirects are checked before parsing; redirected profiles are not accepted.
                if normalize_profile_url(driver.current_url) != url:
                    raise ValueError("Profile redirected")
                WebDriverWait(driver, args.timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.details"))
                )
                # Recheck after the wait in case client-side navigation occurred.
                if normalize_profile_url(driver.current_url) != url:
                    raise ValueError("Profile redirected while waiting")
                contacts = parse_contacts(driver.page_source, url)
                if not contacts:
                    raise ValueError("No named contacts; empty page or changed markup")
            except (TimeoutException, WebDriverException, ValueError) as exc:
                unresolved_pages += 1
                reason = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
                print(
                    f"Unresolved {index + 1}/{total_pages} ({url}): {reason}; continuing.",
                    file=sys.stderr,
                )
                continue
            inserted += save_contacts(connection, contacts)
            parsed_pages += 1
            print(f"Processed {index + 1}/{total_pages} requested profiles.")
        print(
            f"Run summary: requested={total_pages}, parsed={parsed_pages}, "
            f"unresolved={unresolved_pages}, inserted={inserted}. Database: {database}"
        )
        return 1 if unresolved_pages else 0
    finally:
        try:
            if driver is not None:
                driver.quit()
        finally:
            connection.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bounded 11888 extraction and offline demo")
    commands = parser.add_subparsers(dest="command", required=True)
    scrape_parser = commands.add_parser("scrape", help="Parse fictional demo or explicit profiles")
    source = scrape_parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--demo", action="store_true", help="Use fictional HTML; no browser/network")
    source.add_argument("--urls", type=Path, help="UTF-8 file: one explicit 11888 profile URL per line")
    source.add_argument("--url", action="append", help="One explicit profile URL; repeat for more")
    source.add_argument("--start-id", type=int, help="First numeric ID of an inclusive finite range")
    scrape_parser.add_argument("--end-id", type=int, help="Last numeric ID; required with --start-id")
    scrape_parser.add_argument("--database", type=Path,
                               help="SQLite path; defaults to data/demo.sqlite for demo, data/contacts.sqlite for live")
    scrape_parser.add_argument("--max-pages", "--max-urls", type=int, default=100,
                               help="Positive URL/range limit (default: 100); raise explicitly for longer runs")
    scrape_parser.add_argument("--delay", type=float, default=3.0, help="Seconds between pages, minimum 2")
    scrape_parser.add_argument("--timeout", type=float, default=20.0, help="Page and selector timeout in seconds")
    scrape_parser.add_argument("--proxy", help="Optional single Chrome proxy server; default is direct")
    export_parser = commands.add_parser("export", help="Stream the new SQLite schema to CSV")
    export_parser.add_argument("--database", type=Path, required=True)
    export_parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "scrape":
            return scrape(args)
        count = export_csv(args.database, args.output)
        print(f"Exported {count} records to {args.output}.")
        return 0
    except KeyboardInterrupt:
        print("Interrupted; completed pages remain saved.", file=sys.stderr)
        return 130
    except Exception as exc:
        # Fatal configuration/database/browser startup errors end the run.
        print(f"Error ({type(exc).__name__}): {exc}", file=sys.stderr)
        return 1
