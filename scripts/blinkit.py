import logging
from selenium.common.exceptions import WebDriverException, NoSuchElementException, TimeoutException
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import (
    WebDriverException, NoSuchElementException, TimeoutException, ElementClickInterceptedException
)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from scutils import compute_relevance
import time
import json
import re


class BlinkItScrapper:
    def __init__(self, logger, driver):
        self.logger = logger or logging.getLogger(__name__)
        self.driver = driver


   # ---------------- Close any popup ----------------
    def close_popup(self):
        try:
            popup_buttons = self.driver.find_elements(By.CSS_SELECTOR, "div[role='dialog'] button, div[class*='popup'] button, div[class*='Modal'] button")
            for btn in popup_buttons:
                try:
                    if btn.is_displayed():
                        btn.click()
                        logging.info("Popup closed.")
                        time.sleep(1)
                except ElementClickInterceptedException:
                    logging.debug("Popup button click intercepted. Skipping.")
        except Exception as e:
            logging.debug(f"No popup detected: {e}")

    # ---------------- Open Blinkit ----------------
    def open_blinkit(self, url="https://blinkit.com/s/"):
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                logging.debug(f"Attempt {attempt}: Opening {url}")
                self.driver.get(url)
                # Detect location button
                WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn.location-box.mask-button"))
                ).click()
                logging.info("Clicked Detect My Location button")
                time.sleep(2)
                return True
            except (WebDriverException, TimeoutException) as e:
                logging.error(f"Error opening {url}: {e}")
                if attempt < max_retries:
                    logging.debug("Retrying after 5 seconds...")
                    time.sleep(2)
                else:
                    logging.critical("Max retries reached. Could not open page.")
                    return False
        
    # ---------------- Perform Search ----------------
    def search_product(self,product_name):
        self.user_input = product_name
        try:
            logging.debug(f"Searching for product: {product_name}")
            search_box = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "input.SearchBarContainer__Input-sc-hl8pft-3")
                )
            )
            search_box.clear()
            search_box.send_keys(product_name)
            time.sleep(2)
            search_box.send_keys(Keys.ENTER)
            logging.info("BI Search submitted successfully.")
            time.sleep(2)
            self.close_popup()
        except (NoSuchElementException, TimeoutException) as e:
            logging.error(f"Search input field not found on blinkit: {e}")


    # ---------------- Extract Products ----------------
    def extract_products(self):
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                all_products = []
                filtered_products = []

                wait = WebDriverWait(self.driver, 15)
                products = wait.until(
                    EC.presence_of_all_elements_located(
                        (By.CSS_SELECTOR, "div[role='button'][tabindex='0']")
                    )
                )
                logging.info(f"Total products found: {len(products)}")

                for idx, prod in enumerate(products, start=1):
                    # --- Brand & Item Name ---
                    try:
                        title_elem = prod.find_element(
                            By.CSS_SELECTOR,
                            "div.tw-text-300.tw-font-semibold.tw-line-clamp-2"
                        )
                        title_text = title_elem.text.strip() or title_elem.get_attribute("outerHTML")
                        if title_text:
                            parts = title_text.split()
                            brand = parts[0]
                            item_name = " ".join(parts[1:]) if len(parts) > 1 else "N/A"
                        else:
                            brand = "N/A"
                            item_name = "N/A"
                    except:
                        brand = "N/A"
                        item_name = "N/A"

                    # --- Packing ---
                    try:
                        packing_elem = prod.find_element(By.CSS_SELECTOR, "div.tw-text-200.tw-font-medium.tw-line-clamp-1")
                        packing = packing_elem.text.strip() or packing_elem.get_attribute("outerHTML")
                    except:
                        packing = "N/A"

                    # --- Price ---
                    price = "N/A"
                    try:
                        price_candidates = prod.find_elements(By.CSS_SELECTOR, "div.tw-text-200.tw-font-semibold")
                        for elem in price_candidates:
                            text_val = elem.text.strip()
                            if text_val.startswith("₹"):
                                price = text_val
                                break
                            outer_html = elem.get_attribute("outerHTML")
                            match = re.search(r"₹\s*\d+", outer_html)
                            if match:
                                price = match.group()
                                break
                    except:
                        price = "N/A"

                    # --- Relevance ---
                    relevance = compute_relevance(self.user_input, brand, item_name,packing, logger=self.logger)
                    logging.debug(f"Product {idx} relevance: {relevance}%")

                    product_data = {
                        "brand": brand,
                        "item_name": item_name,
                        "packing": packing,
                        "price": price,
                        "relevance": relevance
                    }
                    all_products.append(product_data)
                    if relevance >= 50:
                        filtered_products.append(product_data)

                # If no product has relevance >=50, take top 5
                if not filtered_products:
                    filtered_products = sorted(all_products, key=lambda x: x["relevance"], reverse=True)[:5]
                    logging.info("No product with relevance >=50%, taking top 5 products by relevance.")
                else:
                    filtered_products.sort(key=lambda x: x["relevance"], reverse=True)

                # If price missing, refresh search and retry
                missing_price = any(p["price"] == "N/A" for p in filtered_products)
                if missing_price and attempt < max_retries:
                    logging.info("Some products missing price. Refreshing and retrying...")
                    self.driver.refresh()
                    time.sleep(5)
                    self.search_product(self.user_input)
                    continue

                # Save JSON to file
                with open("results_blinkit.json", "w", encoding="utf-8") as f:
                    json.dump(filtered_products, f, indent=4, ensure_ascii=False)

                logging.info("Filtered products saved to results_blinkit.json")
                print("\nFiltered products JSON array (sorted by relevance):")
                print(json.dumps(filtered_products, indent=4, ensure_ascii=False))
                
                return filtered_products  # Return for headless mode handling

            except TimeoutException:
                logging.error(f"Timed out waiting for product containers. Attempt {attempt} of {max_retries}.")
                if attempt < max_retries:
                    logging.info("Refreshing page and retrying...")
                    self.driver.refresh()
                    time.sleep(5)
                    self.search_product( self.user_input)
                else:
                    logging.critical("Max retries reached. Could not load products.")
                    return []  # Return empty list on failure

   