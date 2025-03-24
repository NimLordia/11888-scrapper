import random
import time
import sqlite3
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service

# --- Setup SQLite Database ---
conn = sqlite3.connect('11888_data.db')
cursor = conn.cursor()
cursor.execute('''
CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    location TEXT,
    phones TEXT,
    page_url TEXT,
    page INTEGER
)
''')
conn.commit()

# --- Setup Selenium WebDriver ---
service = Service()  # Specify chromedriver path if needed
options = webdriver.ChromeOptions()
options.add_argument('--headless')
options.add_argument("--disable-gpu")
options.add_argument("--log-level=3")
driver = webdriver.Chrome(service=service, options=options)

proxies = [
    "http://proxy1:port",  # Replace with your actual proxy addresses
    "http://proxy2:port",
    "http://proxy3:port"
]

def create_driver(proxy):
    """Creates a new Chrome WebDriver instance with the given proxy."""
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument("--disable-gpu")
    options.add_argument("--log-level=3")
    if proxy:
        options.add_argument(f'--proxy-server={proxy}')
    return webdriver.Chrome(service=service, options=options)

def has_data(page_number):
    """
    Returns True if the page at the given number contains data.
    If there's no data, the site may redirect away from the search URL.
    """
    url = f"https://www.11888.gr/search/white_pages/{page_number}/"
    driver.get(url)
    time.sleep(0.2)  # Allow time for page to load
    if "search/white_pages" not in driver.current_url:
        return False
    try:
        element = driver.find_element(By.CSS_SELECTOR, "div.details")
        return bool(element.text.strip())
    except Exception:
        return False

scrape_page = 1  # Change this number for the first page to check

while scrape_page < 50000000:  # or use "while True" if desired
    # Rotate IP by selecting a random proxy
    proxy = random.choice(proxies)
    driver = create_driver(proxy)
    
    url = f"https://www.11888.gr/search/white_pages/{scrape_page}/"
    print(f"Scraping page: {scrape_page} using proxy: {proxy} - {url}")
    driver.get(url)
    time.sleep(0.2)
    
    details_containers = driver.find_elements(By.CSS_SELECTOR, "div.details")
    if not details_containers:
        print(f"No details found on page {scrape_page}.")
    else:
        print(f"Data found on page {scrape_page}.")
        for container in details_containers:
            driver.execute_script("arguments[0].scrollIntoView();", container)
            # --- Extract the name ---
            try:
                name_elem = container.find_element(By.CSS_SELECTOR, "div.share_header div.name h1")
                name = name_elem.text.strip()
            except Exception as e:
                print("Error extracting name:", e)
                name = "N/A"
            
            # --- Extract the location ---
            try:
                location_elem = container.find_element(By.CSS_SELECTOR, "div.location div.address")
                location = location_elem.text.strip()
            except Exception as e:
                print("Error extracting location:", e)
                location = "N/A"
            
            # --- Extract phone numbers ---
            try:
                phone_elems = container.find_elements(By.CSS_SELECTOR, "div.phones a.tel-link")
                phones_list = []
                for phone_elem in phone_elems:
                    href = phone_elem.get_attribute("href")
                    if href and "tel:" in href:
                        number = href.split("tel:")[-1].strip()
                        phones_list.append(number)
                phones = ", ".join(phones_list) if phones_list else "N/A"
            except Exception as e:
                print("Error extracting phones:", e)
                phones = "N/A"
            
            page_url = driver.current_url
            
            cursor.execute(
                "INSERT INTO contacts (name, location, phones, page_url, page) VALUES (?, ?, ?, ?, ?)",
                (name, location, phones, page_url, scrape_page)
            )
            conn.commit()
            print(f"Inserted: {name} | {location} | {phones} | {page_url}")
    
    driver.quit()  # Close the driver to change IP on the next iteration
    scrape_page += 1

print("Scraping complete!")
conn.close()