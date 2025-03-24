import sqlite3
import csv

# Connect to the SQLite database
conn = sqlite3.connect('11888_data.db')
cursor = conn.cursor()

# Execute a query to select all data from the contacts table
cursor.execute("SELECT * FROM contacts")
rows = cursor.fetchall()

# Get the column headers from the cursor description
headers = [description[0] for description in cursor.description]

# Write the data to a CSV file
with open('contacts.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(headers)  # Write header row
    writer.writerows(rows)    # Write data rows

conn.close()
print("Data has been exported to contacts.csv")
