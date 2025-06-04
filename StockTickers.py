from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import json
import time

BASE_URL = "https://www.londonstockexchange.com/indices/ftse-100/constituents/table"

# Configure Selenium to use headless Chrome
options = Options()
options.add_argument("--headless")
#options.add_argument("--disable-gpu")

# Initialize the WebDriver
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
driver.get(BASE_URL)
time.sleep(5)  

cookies_button_xpath = '/html/body/div/div[2]/div/div[1]/div/div[2]/div/button[2]'
cookies_button = driver.find_elements(By.XPATH, cookies_button_xpath)

if cookies_button:
    # Click the cookies button if it is present
    cookies_button[0].click()
    print("Cookies button clicked.")
else:
    print("Cookies button not found, no click needed.")

time.sleep(5)

# Determine the total number of pages
try:
    pagination = driver.find_element(By.CLASS_NAME, "paginator")
    pages = pagination.find_elements(By.TAG_NAME, "a")
    TOTAL_PAGES = int(pages[-1].text)  # Assuming the last page number is second to last item
except Exception as e:
    print(f"Error determining total pages: {e}")
    TOTAL_PAGES = 1  # Default to 1 if pagination not found

print(f"Total pages found: {TOTAL_PAGES}")

all_stocks = []

try:
    wait = WebDriverWait(driver, 10)
    for page in range(1, TOTAL_PAGES + 1):
        print(f"Processing page {page}")
        
        # Number of Rows in Table
        rows = driver.find_elements(By.CSS_SELECTOR, "table.full-width.ftse-index-table-table tbody tr")
        print(f"Total Rows in Table = {rows}")

        for r in rows:
            try:
                cols = r.find_elements(By.TAG_NAME, "td")
                code = cols[0].text.strip()
                name = cols[1].text.strip()
                all_stocks.append({"name": name, "code": code})
            except Exception as e:
                print("Error reading row:", e)

        # Click next button if not on last page
        if page < TOTAL_PAGES:
            next_button = wait.until(EC.element_to_be_clickable((By.XPATH, 
                    f'/html/body/app-root/app-handshake/div/app-page-content/app-filter-toggle/app-ftse-index-table/section/app-paginator/div/a[{page+1}]')))

            # Scroll into view
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button)
            time.sleep(1)  # Give time to finish scrolling
            next_button.click()
            time.sleep(1)

finally:
    driver.quit()

# Save to JSON
with open("ftse100_stocks.json", "w", encoding="utf-8") as f:
    json.dump(all_stocks, f, indent=4)

print("Saved ftse100_stocks.json")
