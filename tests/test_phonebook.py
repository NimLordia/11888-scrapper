import csv
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from phonebook.cli import build_parser, scrape
from phonebook.core import (
    Contact, export_csv, initialize_database, normalize_profile_url,
    parse_contacts, profile_range, read_profile_urls, save_contacts,
)


class ParserTests(unittest.TestCase):
    def test_fixture_and_missing_optional_fields(self):
        fixture = Path(__file__).parents[1] / "phonebook" / "fixtures" / "demo.html"
        records = parse_contacts(fixture.read_text(encoding="utf-8"), "https://example.invalid/demo")
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].phones, ("000-DEMO-ALPHA",))
        html = '<div class="details"><div class="share_header"><div class="name"><h1> Fictional Person </h1></div></div></div>'
        self.assertEqual(parse_contacts(html, "demo")[0], Contact("Fictional Person", "", (), "demo"))
        self.assertEqual(parse_contacts('<div class="details">No name</div>', "demo"), [])

    def test_phone_links_deduplicate_and_ignore_non_telephone_links(self):
        html = '''<div class="details"><div class="share_header"><div class="name"><h1>Demo</h1></div></div>
        <div class="phones"><a class="tel-link" href="tel:000-DEMO">one</a>
        <a class="tel-link" href="TEL:000-DEMO">duplicate</a>
        <a class="tel-link" href="https://example.invalid/tel:fake">ignored</a></div></div>'''
        self.assertEqual(parse_contacts(html, "demo")[0].phones, ("000-DEMO",))


class URLTests(unittest.TestCase):
    def test_normalization(self):
        self.assertEqual(normalize_profile_url("https://11888.gr/search/white_pages/123"),
                         "https://www.11888.gr/search/white_pages/123/")

    def test_reject_unexpected_urls(self):
        for value in [
            "http://www.11888.gr/search/white_pages/1/",
            "https://www.11888.gr.attacker.invalid/search/white_pages/1/",
            "https://user@www.11888.gr/search/white_pages/1/",
            "https://www.11888.gr/search/white_pages/1/?x=1",
            "https://www.11888.gr/search/white_pages/1/#x",
            "https://www.11888.gr/search/white_pages/../",
            "https://www.11888.gr/",
        ]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_profile_url(value)

    def test_explicit_list_dedup_and_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "urls.txt"
            path.write_text("# test URLs, never fetched\nhttps://11888.gr/search/white_pages/1\n"
                            "https://www.11888.gr/search/white_pages/1/\n", encoding="utf-8")
            self.assertEqual(len(read_profile_urls(path, 1)), 1)
            path.write_text(path.read_text() + "https://11888.gr/search/white_pages/2/\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                read_profile_urls(path, 1)
            with self.assertRaises(ValueError):
                read_profile_urls(path, 0)

    def test_range_is_inclusive_lazy_and_requires_explicit_limit_increase(self):
        urls = profile_range(10, 12)
        self.assertIs(iter(urls), urls)
        self.assertEqual(list(urls), [f"https://www.11888.gr/search/white_pages/{number}/" for number in (10, 11, 12)])
        with self.assertRaises(ValueError):
            profile_range(1, 101)
        self.assertEqual(len(list(profile_range(1, 101, 101))), 101)
        for bounds in [(0, 1), (2, 1)]:
            with self.subTest(bounds=bounds), self.assertRaises(ValueError):
                profile_range(*bounds)


class StorageTests(unittest.TestCase):
    def test_repeat_records_and_phone_order_do_not_duplicate(self):
        connection = sqlite3.connect(":memory:")
        try:
            initialize_database(connection)
            first = Contact("Fictional", "Nowhere", ("000-B", "000-A"), "demo")
            second = Contact("Fictional", "Nowhere", ("000-A", "000-B"), "demo")
            self.assertEqual(save_contacts(connection, [first]), 1)
            self.assertEqual(save_contacts(connection, [second]), 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM contacts").fetchone()[0], 1)
        finally:
            connection.close()

    def test_csv_unicode_quoting_and_formula_neutralization(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "test.sqlite"
            output = Path(directory) / "nested" / "contacts.csv"
            connection = sqlite3.connect(database)
            try:
                initialize_database(connection)
                save_contacts(connection, [Contact("=FICTIONAL()", 'Δοκιμή, "Example"', ("000-DEMO",), "demo")])
            finally:
                connection.close()
            self.assertEqual(export_csv(database, output), 1)
            with output.open(encoding="utf-8-sig", newline="") as source:
                rows = list(csv.reader(source))
            self.assertEqual(rows[1], ["'=FICTIONAL()", 'Δοκιμή, "Example"', "000-DEMO", "demo"])
            with self.assertRaises(ValueError):
                export_csv(database, database)

    def test_missing_database_does_not_create_empty_file(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "missing.sqlite"
            with self.assertRaises(sqlite3.OperationalError):
                export_csv(database, Path(directory) / "out.csv")
            self.assertFalse(database.exists())

    def test_legacy_database_is_rejected_without_modification(self):
        connection = sqlite3.connect(":memory:")
        try:
            connection.execute("CREATE TABLE contacts (id INTEGER PRIMARY KEY, name TEXT)")
            connection.execute("INSERT INTO contacts (name) VALUES ('Fictional Legacy')")
            connection.commit()
            with self.assertRaisesRegex(ValueError, "legacy 11888_data.db"):
                initialize_database(connection)
            self.assertEqual(connection.execute("SELECT name FROM contacts").fetchone()[0], "Fictional Legacy")
        finally:
            connection.close()


class LifecycleTests(unittest.TestCase):
    def test_demo_and_live_default_databases_are_separate(self):
        previous_directory = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                with patch("phonebook.cli.create_driver", side_effect=RuntimeError("No real browser")) as create:
                    self.assertEqual(scrape(build_parser().parse_args(["scrape", "--demo"])), 0)
                    create.assert_not_called()
                    self.assertTrue(Path("data/demo.sqlite").exists())
                    self.assertFalse(Path("data/contacts.sqlite").exists())
                    args = build_parser().parse_args(["scrape", "--url", "https://www.11888.gr/search/white_pages/1/"])
                    with self.assertRaisesRegex(RuntimeError, "No real browser"):
                        scrape(args)
                    self.assertTrue(Path("data/contacts.sqlite").exists())
            finally:
                os.chdir(previous_directory)

    def test_demo_never_creates_browser(self):
        with tempfile.TemporaryDirectory() as directory:
            args = build_parser().parse_args(["scrape", "--demo", "--database", str(Path(directory) / "demo.sqlite")])
            with patch("phonebook.cli.create_driver") as create:
                self.assertEqual(scrape(args), 0)
                self.assertEqual(scrape(args), 0)
                create.assert_not_called()

    def test_browser_is_closed_when_fetch_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            urls = Path(directory) / "urls.txt"
            urls.write_text("https://www.11888.gr/search/white_pages/1/\n", encoding="utf-8")
            database = Path(directory) / "contacts.sqlite"
            args = build_parser().parse_args(["scrape", "--urls", str(urls), "--database", str(database)])
            driver = Mock()
            driver.get.side_effect = RuntimeError("Offline simulated browser error")
            with patch("phonebook.cli.create_driver", return_value=driver):
                with self.assertRaisesRegex(RuntimeError, "Offline simulated"):
                    scrape(args)
            driver.quit.assert_called_once()
            # Windows refuses this rename if the database handle remains open.
            database.rename(Path(directory) / "closed.sqlite")

    def test_scan_continues_after_gap_and_reports_incomplete_run(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "contacts.sqlite"
            args = build_parser().parse_args([
                "scrape", "--start-id", "10", "--end-id", "12", "--database", str(database),
                "--proxy", "http://proxy.example:8080",
            ])
            fixture = (Path(__file__).parents[1] / "phonebook" / "fixtures" / "demo.html").read_text(encoding="utf-8")
            driver = Mock()
            def navigate(url):
                driver.current_url = url
                driver.page_source = "<html>Unrecognized gap</html>" if url.endswith("/11/") else fixture
            driver.get.side_effect = navigate
            with patch("phonebook.cli.create_driver", return_value=driver) as create, \
                    patch("selenium.webdriver.support.ui.WebDriverWait") as wait, \
                    patch("phonebook.cli.time.sleep"):
                wait.return_value.until.return_value = True
                self.assertEqual(scrape(args), 1)
                create.assert_called_once_with(20.0, "http://proxy.example:8080")
            self.assertEqual(driver.get.call_count, 3)
            driver.quit.assert_called_once()
            connection = sqlite3.connect(database)
            try:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM contacts").fetchone()[0], 4)
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
