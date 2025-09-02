import logging
import sys
import argparse
import signal
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bigbasket import BBScrapper
from blinkit import BlinkItScrapper
from swiggy import SwiggyScrapper
from multiprocessing import Pool
import os
import tempfile

# ---------------- Logging Setup ----------------
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

logging.getLogger("selenium.webdriver.remote.remote_connection").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

driver = None
headless_mode = False

# ---------------- Cleanup ----------------
def cleanup(sig=None, frame=None, exit_program=True):
    logging.info("Termination signal received. Closing Chrome safely...")
    global driver
    if driver:
        try:
            driver.quit()
            logging.info("Chrome closed successfully.")
        except Exception as e:
            logging.error(f"Error closing Chrome: {e}")
    if exit_program:
        sys.exit(0)

signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

# ---------------- CLI Arguments ----------------
def parse_arguments():
    parser = argparse.ArgumentParser(description="Product Scraper")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Chrome in headless mode (no GUI) and exit automatically after scraping"
    )
    parser.add_argument(
        "--product",
        type=str,
        help="Product name to search for (required in headless mode)"
    )
    return parser.parse_args()

# ---------------- Selenium Setup ----------------
def create_driver(headless=False):
    chrome_options = Options()
    chrome_options.add_argument("--start-maximized")

    if headless:
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        )
        logging.info("Running Chrome in headless mode (stealth patched)")

     # Use unique temp user-data-dir for each process
    user_data_dir = tempfile.mkdtemp()
    chrome_options.add_argument(f"--user-data-dir={user_data_dir}")

    

    # Use the driver installed in the image
    driver_path = os.getenv("CHROMEDRIVER_PATH")  # or wherever it is in the image
    service = Service(driver_path)

    driver_instance = webdriver.Chrome(service=service, options=chrome_options)

    if headless:
        driver_instance.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            """
        })

    return driver_instance

# ---------------- Scraper Runners ----------------
def run_bigbasket(args):
    product_name, headless = args
    driver = create_driver(headless=headless)
    scrapper = BBScrapper(logging.getLogger(), driver)
    logging.info(f"BigBasket scraper will start now.")
    try:
        if scrapper.open_bigbasket():
            logging.info(f"BigBasket is opened.")
            scrapper.search_product(product_name)
            scrapper.print_search_results()
            logging.info(f"product is searched on BigBasket.")
            products = scrapper.extract_products()
            logging.info(f"{products.length} products found on BigBasket.")
            return {"source": "BigBasket", "products": products}
        else:
            logging.error("Failed to open BigBasket.")
            return {"source": "BigBasket", "products": []}
    except Exception as e:
        logging.error(f"BigBasket scraper failed: {e}")
        return {"source": "BigBasket", "products": []}
    finally:
        driver.quit()

def run_blinkit(args):
    product_name, headless = args
    driver = create_driver(headless=headless)
    scrapper = BlinkItScrapper(logging.getLogger(), driver)
    try:
        if scrapper.open_blinkit():
            scrapper.search_product(product_name)
            products = scrapper.extract_products()
            return {"source": "BlinkIt", "products": products}
        else:
            logging.error("Failed to open BlinkIt.")
            return {"source": "BlinkIt", "products": []}
    except Exception as e:
        logging.error(f"BlinkIt scraper failed: {e}")
        return {"source": "BlinkIt", "products": []}
    finally:
        driver.quit()

def run_swiggy(args):
    product_name, headless = args
    driver = create_driver(headless=headless)
    scrapper = SwiggyScrapper(logging.getLogger(), driver)
    try:
        if scrapper.open_swiggy():
            scrapper.search_product(product_name)
            products = scrapper.extract_products()
            return {"source": "Swiggy", "products": products}
        else:
            logging.error("Failed to open Swiggy Instamart.")
            return {"source": "Swiggy", "products": []}
    except Exception as e:
        logging.error(f"Swiggy scraper failed: {e}")
        return {"source": "Swiggy", "products": []}
    finally:
        driver.quit()

# ---------------- Worker Wrapper ----------------
def worker(task):
    func, args = task
    return func(args)

# ---------------- Main ----------------
if __name__ == "__main__":
    args = parse_arguments()
    headless_mode = args.headless

    if headless_mode and args.product:
        product_name = args.product
        logging.info(f"scrapper Running in headless mode with product: {product_name}")
    else:
        product_name = input("Enter product to compare : ")

    tasks = [
        (run_bigbasket, (product_name, headless_mode)),
        (run_blinkit, (product_name, headless_mode)),
        (run_swiggy, (product_name, headless_mode)),
    ]

    with Pool(processes=3) as pool:
        results = pool.map(worker, tasks)

    # Safely log results
    for result in results:
        if result and "products" in result:
            logging.info(f"Source: {result['source']} | Found {len(result['products'])} products")
        else:
            logging.warning(f"A scraper returned no results: {result}")

    if headless_mode:
        print("Scraping completed in headless mode.")
        cleanup(exit_program=False)
    else:
        logging.info("Script finished. Waiting for user to terminate with Ctrl+C...")
        cleanup(exit_program=False)
