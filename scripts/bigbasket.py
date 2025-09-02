import logging
from selenium.common.exceptions import WebDriverException, NoSuchElementException, TimeoutException
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException, NoSuchElementException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from scutils import compute_relevance
import time
import json
import random


class BBScrapper:
    def __init__(self, logger, driver):
        self.logger = logger or logging.getLogger(__name__)
        self.driver = driver
        self.max_scrap = 5
        

    # ---------------- Open BigBasket ----------------
    # ---------------- Open BigBasket with Enhanced Anti-Detection ----------------
    def open_bigbasket(self, url="https://www.bigbasket.com/"):
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                self.logger.debug(f"Attempt {attempt}: Opening {url}")
                
                # Add random delay before loading
                #time.sleep(random.uniform(1, 3))
                
                self.driver.get(url)
                
                # Wait for page to fully load
                WebDriverWait(self.driver, 15).until(
                    lambda driver: driver.execute_script("return document.readyState") == "complete"
                )
                
                # Additional wait for dynamic content
                #time.sleep(random.uniform(3, 6))
                
                # Check if we're on the correct page (not blocked/redirected)
                current_url = self.driver.current_url
                if "bigbasket.com" in current_url.lower():
                    self.logger.debug("Page loaded successfully.")
                    return True
                else:
                    self.logger.warning(f"Unexpected redirect to: {current_url}")
                    if attempt < max_retries:
                        time.sleep(2)
                        continue
                    
            except WebDriverException as e:
                self.logger.error(f"Error opening {url}: {e}")
                if attempt < max_retries:
                    self.logger.debug("Retrying after 5 seconds...")
                    time.sleep(2)
                else:
                    self.logger.critical("Max retries reached. Exiting.")
                    return False
        return False
    
    # ---------------- Perform Search ----------------
    def search_product(self,search_inp):
        self.search_inp = search_inp
        try:
            self.logger.debug(f"BB Searching for product: {search_inp}")
            #self.driver.save_screenshot("bigbasket-ss.png")
            search_box = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "input[placeholder='Search for Products...']")
                )
            )
            #search_box = self.driver.find_element(By.CSS_SELECTOR, "input[placeholder='Search for Products...']")
            search_box.clear()
            #time.sleep(random.uniform(0.5, 1.5))
            #search_box.send_keys(self.search_inp)
            # Type with random delays between characters
            for char in search_inp:
                search_box.send_keys(char)
                time.sleep(random.uniform(0.05, 0.2))
            
            #time.sleep(random.uniform(1, 2))
            search_box.send_keys(Keys.ENTER)


             # Additional wait for results
            #time.sleep(random.uniform(3, 6))
            self.logger.debug("BB Search submitted successfully.")
        except NoSuchElementException:
            self.logger.error("BB Search input field not found on Bigbasket.")

    # ---------------- Get Search Results Count ----------------
    def print_search_results(self):
        try:
            self.logger.debug("BB Waiting for results to load...")

            result_count_elem = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "span[class*='CategoryInfo___StyledLabel2']"))
            )
            count_text = result_count_elem.text.strip()
            
            try:
                self.max_scrap = int(count_text)
            except (ValueError, TypeError):
                self.max_scrap = 5

            result_text_elem = WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "h2[class*='CategoryInfo___StyledH']"))
            )
            result_text = result_text_elem.text.strip()

            self.logger.info(f"BB Search Results: {count_text} {result_text}")
            print(f"\nTotal Products Found: {count_text} {result_text}\n")

        except TimeoutException:
            self.logger.error("BB Timed out waiting for search results.")

    # ---------------- Extract Products ----------------
    def extract_products(self):
        products = []
        try:
            self.logger.debug("BB Extracting product details...")

            first_card = WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "li[class*='PaginateItems']"))
            )

            container = first_card.find_element(By.XPATH, "..")
            children = container.find_elements(By.XPATH, "./*")

            for i, child in enumerate(children):
                if i >= self.max_scrap:
                    break
                child_class = child.get_attribute("class") or ""

                if "PaginateItems" in child_class:
                    card = child
                    spans = card.find_elements(By.TAG_NAME, "span")
                    unavailable = any(
                        sp.text.strip() == "Currently unavailable" and "Tags___StyledLabel2" in (sp.get_attribute("outerHTML") or "")
                        for sp in spans
                    )
                    if unavailable:
                        continue

                    try:
                        brand = card.find_element(By.CSS_SELECTOR, "span[class*='BrandName___StyledLabel2']").text.strip()
                    except:
                        brand = ""
                    try:
                        item_name = card.find_element(By.CSS_SELECTOR, "h3.block.m-0.line-clamp-2").text.strip()
                    except:
                        item_name = ""


                    # Calculate relevance (brand + item only)
                    relevance = compute_relevance(self.search_inp, brand, item_name, '',logger=self.logger)

                    if relevance >= 30:

                        # --- Updated Packing Logic ---

                        # --- If PackSelector dropdown exists, click and fetch PackChanger options ---
                        
                        try:
                            pack_button = card.find_element(By.CSS_SELECTOR, "button[class*='Button'][class*='PackChanger']")
                            self.driver.execute_script("arguments[0].click();", pack_button)  # safer than .click()
                            time.sleep(1)  # wait for popup to appear
                            print(f"PackChanger button found for {item_name} and clicked.")
                            try:
                                popup_ul = self.driver.find_element(By.CSS_SELECTOR, '[id*="headlessui-listbox-options"]')
                                print("Popup UL found ✅")
                                # Get all LI children havinf div as child of that UL 
                                li_elements = popup_ul.find_elements(By.CSS_SELECTOR, 'li > div')
                            except NoSuchElementException:
                                print("Popup UL not found ❌")
                            

                            print(f"Found {len(li_elements)} li children (packing) for {item_name}")
                            for li in li_elements:
                                try:
                                    # Find first div child with class 'packChanger' inside li
                                    parent_div = li.find_element(By.CSS_SELECTOR, "div:first-child")
                                
                                    packing_div = parent_div.find_element(By.CSS_SELECTOR, "div:first-child")
                                    
                                    print("Packing : ", packing_div.get_attribute("innerHTML"))
                                    packing = packing_div.get_attribute("innerHTML")

                                    price_div = li.find_element(By.CSS_SELECTOR, "div:nth-child(2)")
                                    '''print("Tag:", price_div.tag_name)
                                    print("Class:", price_div.get_attribute('class'))
                                    print("Outer HTML:", price_div.get_attribute('outerHTML'))
                                    print("Inner HTML:", price_div.get_attribute('innerHTML'))
                                    print("Text:", price_div.text)'''


                                    price_span = price_div.find_element(By.CSS_SELECTOR, "div span:nth-of-type(2)")
                                    
                                    print("Price : ", price_span.get_attribute("innerHTML"))
                                    price = price_span.get_attribute("innerHTML")

                                    products.append({
                                        "brand": brand,
                                        "item_name": item_name,
                                        "packing": packing,
                                        "price": price,
                                        "relevance": relevance
                                    })

                                    
                                except:
                                    print("packing/price details div not found ❌")
                                    # skip if structure not found
                                    continue
                        except NoSuchElementException:
                            print("PackChanger button not found")
                            try:
                                # Try PackChanger first
                                packing = card.find_element(
                                    By.CSS_SELECTOR,
                                    "span.PackChanger___StyledLabel-sc-newjpv-1"
                                ).text.strip()
                            except NoSuchElementException:
                                # Fallback to PackSelector
                                packing = card.find_element(
                                    By.CSS_SELECTOR,
                                    "span.PackSelector___StyledLabel-sc-1lmu4hv-0 span.Label-sc-15v1nk5-0.gJxZPQ"
                                ).text.strip()
                                print("Packing from PackSelector could not be extracted: ")
                                

                        try:
                            price_container = card.find_element(By.CSS_SELECTOR, "div.Pricing___StyledDiv-sc-pldi2d-0")
                            price = price_container.find_element(By.CSS_SELECTOR, "span:first-child").text.strip()
                        except:
                            price = ""

                        if not price or price.lower() in ["null", "undefined"]:
                            self.logger.info(f"BB Skipping '{item_name}' because price is missing or invalid.")
                            continue

                        

                        products.append({
                            "brand": brand,
                            "item_name": item_name,
                            "packing": packing,
                            "price": price,
                            "relevance": relevance
                        })
                    else:
                        self.logger.info(f"BB Skipping '{item_name}' due to low relevance ({relevance}%)")



                    

                else:
                    p_elements = child.find_elements(By.TAG_NAME, "p")
                    if any("more items from" in (p.text or "").lower() or "more items from" in (p.get_attribute("outerHTML") or "").lower() for p in p_elements):
                        self.logger.info("Encountered 'More items from' separator. Stopping scraping further items.")
                        break

            # --- Relevance filtering ---
            filtered_products = [p for p in products if p["relevance"] >= 50]

            if not filtered_products:
                filtered_products = sorted(products, key=lambda x: x["relevance"], reverse=True)[:5]
                self.logger.info("BB No products above 50% relevance. Using top 5 fallback.")

            

            # Combine old and new data
            combined_data = filtered_products
            
            # Remove duplicates
            unique_products = []
            seen_tuples = set()
            for product in combined_data:
                # Create a tuple of the relevant fields to check for uniqueness
                # Assuming 'brand', 'item_name', and 'packing' define a unique product
                item_tuple = (product.get("brand"), product.get("item_name"), product.get("packing"))
                if item_tuple not in seen_tuples:
                    unique_products.append(product)
                    seen_tuples.add(item_tuple)


            with open("results_bigbasket.json", "w", encoding="utf-8") as f:
                json.dump(unique_products, f, indent=4, ensure_ascii=False)
            self.logger.info(f"Saved {len(unique_products)} unique products to 'results_bigbasket.json'")

        except TimeoutException:
            self.logger.error("Timed out waiting for product cards.")
        except Exception:
            self.logger.exception("exception in extracting bigbasket for product cards." )
        logging.info(f"Scraped {len(products)} products on bigbasket.")
        return products