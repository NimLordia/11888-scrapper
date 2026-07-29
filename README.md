# 11888 Greek Phone Book Scraper

A web scraper for the Greek phone directory **11888**.

## Overview

The scraper collects phone book data and stores the results in a local SQLite database.

## Exporting to CSV

Use the included `sqliteToCSV.py` script to convert the generated SQLite database into a CSV file.

```bash
python sqliteToCSV.py
```

## Output

The project can produce:

* An SQLite database containing the scraped data.
* A CSV file generated from the SQLite database.
