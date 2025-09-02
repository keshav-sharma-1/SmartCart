import logging

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


class SwiggyScrapper:
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

    # ---------------- Open Swiggy Instamart ----------------
    def open_swiggy(self, url="https://www.swiggy.com/instamart/search?custom_back=true"):
        max_retries = 5
        for attempt in range(1, max_retries + 1):
            try:
                logging.debug(f"Attempt {attempt}: Opening {url}")
                self.driver.get(url)
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "input[type='search'][data-testid='search-page-header-search-bar-input']")
                    )
                )
                logging.info("Page loaded successfully.")
                self.close_popup()
                return True
            except (WebDriverException, TimeoutException) as e:
                logging.error(f"Error opening {url}: {e}")
                if attempt < max_retries:
                    logging.debug("Retrying after 5 seconds...")
                    time.sleep(5)
                else:
                    logging.critical("Max retries reached. Could not open page.")
                    return False
            except Exception:
                logging.exception("error in opening swiggy")


    # ---------------- Perform Search ----------------
    def search_product(self, product_name):
        self.user_input = product_name
        try:
            logging.debug(f"Searching for product: {product_name}")
            search_box = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "input[type='search'][data-testid='search-page-header-search-bar-input']")
                )
            )
            search_box.clear()
            search_box.send_keys(product_name)
            time.sleep(5)
            search_box.send_keys(Keys.ENTER)
            logging.info("Search submitted successfully.")
            time.sleep(5)
            self.close_popup()
        except (NoSuchElementException, TimeoutException) as e:
            logging.error(f"Search input field not found: {e}")


    # ---------------- Extract Product Details with retry ----------------
    def extract_products(self):
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                all_products = []
                filtered_products = []

                wait = WebDriverWait(self.driver, 5)
                products = wait.until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div[data-testid='default_container_ux4']"))
                )
                logging.info(f"Total products found: {len(products)}")

                missing_price = False

                for idx, prod in enumerate(products, start=1):
                    # --- Brand & Item Name ---
                    try:
                        title_elem = prod.find_element(By.CSS_SELECTOR, "div.sc-aXZVg.kyEzVU._1sPB0")
                        title_text = title_elem.text.strip()
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
                        packing_elem = prod.find_element(By.CSS_SELECTOR, "div._3eIPt, div._1HYm8, div.entQHA")
                        packing = packing_elem.text.strip()
                    except:
                        packing = "N/A"

                    # --- Price ---
                    try:
                        price_elem = prod.find_element(By.CSS_SELECTOR, "div[data-testid='item-offer-price']")
                        price = price_elem.text.strip()
                        if price.lower() == "n/a" or not price:
                            missing_price = True
                    except:
                        price = "N/A"
                        missing_price = True

                    # --- Relevance (brand + packing) ---
                    relevance = compute_relevance(self.user_input, brand,item_name, packing,logger=self.logger)
                    logging.debug(f"Product {idx} relevance: {relevance}% (brand + packing)")

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

                # If any product missing price, refresh and retry
                if missing_price and attempt < max_retries:
                    logging.warning(f"Missing price detected. Refreshing search and retrying attempt {attempt}/{max_retries}...")
                    self.driver.refresh()
                    time.sleep(2)
                    self.search_product(self, self.user_input)
                    continue

                # If no product has relevance >=50, take top 5
                if not filtered_products:
                    filtered_products = sorted(all_products, key=lambda x: x["relevance"], reverse=True)[:5]
                    logging.info("No product with relevance >=50%, taking top 5 products by relevance.")
                else:
                    filtered_products.sort(key=lambda x: x["relevance"], reverse=True)

                # Save JSON to file
                with open("results_swiggyinsta.json", "w", encoding="utf-8") as f:
                    json.dump(filtered_products, f, indent=4, ensure_ascii=False)

                logging.info("Filtered products saved to results_swiggyinsta.json")
                print("\nFiltered products JSON array (sorted by relevance):")
                print(json.dumps(filtered_products, indent=4, ensure_ascii=False))
                break  # success, exit retry loop

            except TimeoutException:
                logging.error(f"Timed out waiting for product containers. Attempt {attempt} of {max_retries}.")
                if attempt < max_retries:
                    logging.info("Refreshing page and retrying...")
                    self.driver.refresh()
                    time.sleep(2)
                    self.search_product(self.driver, self.user_input)
                else:
                    logging.critical("Max retries reached. Could not load products.")
                    break