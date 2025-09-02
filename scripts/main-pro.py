import subprocess
import sys
import glob
import re
import psutil
import signal
import os
from datetime import datetime
import json
import argparse
import logging

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

# ---------------- Logging Setup ----------------
date_str = datetime.now().strftime("%Y%m%d")
log_file_path = os.path.join(LOG_DIR, f"backend-py-{date_str}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file_path),
        logging.StreamHandler(sys.stdout)
    ]
)

def find_scripts():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    all_py_files = glob.glob(os.path.join(script_dir, "*.py"))
    
    scrapers = [f for f in all_py_files if re.search(r"scrapper", f, re.IGNORECASE)]
    comparators = [f for f in all_py_files if re.search(r"comparator", f, re.IGNORECASE)]

    if not scrapers:
        logging.warning(f"No scraper scripts found in {script_dir}")
    if not comparators:
        logging.warning(f"No comparator script found in {script_dir}")

    return scrapers, comparators

def kill_chrome_processes():
    for proc in psutil.process_iter(['name']):
        try:
            if proc.info['name'] and 'chrome' in proc.info['name'].lower():
                proc.kill()
        except Exception:
            pass

def get_log_file():
    return log_file_path

def run_scripts(scripts, user_input, headless_flag):
    log_file = get_log_file()
    for script in scripts:
        logging.info(f"Running {script} (logs -> {log_file}) ...")
        try:
            with open(log_file, "a") as lf:
                lf.write(f"\n\n===== Running {script} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} =====\n")
                cmd = [sys.executable, script]
                if headless_flag:
                    cmd.append("--headless")

                proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=sys.stdout,
                    stderr=subprocess.STDOUT
                )
                try:
                    proc.communicate(input=user_input.encode())
                except KeyboardInterrupt:
                    logging.warning(f"Ctrl+C pressed. Terminating {script}...")
                    proc.kill()
                    kill_chrome_processes()
                    logging.info(f"{script} terminated. Moving to next script...")

                


        except subprocess.CalledProcessError as e:
            logging.error(f"Error running {script}: {e}")

def is_running_from_node():
    try:
        parent = psutil.Process(os.getppid())
        if parent and parent.name().lower().startswith("node"):
            return True
    except Exception:
        pass
    return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--product", type=str, help="Product to search and compare")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode")
    args = parser.parse_args()

    user_input = args.product if args.product else input("Enter product to search and compare: ")

    if is_running_from_node():
        headless_flag = True
        logging.info("Running from Node.js → Defaulting to headless mode")
    else:
        headless_flag = args.headless or input("Run scrapers in headless mode? (y/n): ").strip().lower() == "y"

    scrapers, comparators = find_scripts()

    if not scrapers or not comparators:
        sys.exit(1)

    logging.info("user_input for scrapper is "+ user_input)

    run_scripts(scrapers, user_input, headless_flag)

    comparator_script = comparators[0]
    log_file = get_log_file()
    logging.info(f"Running comparator {comparator_script} (logs -> {log_file}) ...")

    try:
        cmd = [sys.executable, comparator_script]
        

       


        result = subprocess.run(
            [
                sys.executable, 
                comparator_script,
                "--product", user_input,
                "--headless"
            ],
            capture_output=True,
            text=True,
            check=True,
        )


        # Print entire stdout and stderr
        print("[comparator STDOUT]")
        print(result.stdout)

        print("[comparator STDERR]")
        print(result.stderr)

        with open(log_file, "a") as lf:
            lf.write(f"\n\n===== Running comparator {comparator_script} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} =====\n")
            lf.write(result.stdout)
            if result.stderr:
                lf.write("\n[STDERR]\n" + result.stderr)

        output = result.stdout.strip()
        logging.info(f"Comparator output was: {output}")

        json_match = re.search(r'(\{.*\}|\[.*\])', output, re.DOTALL)

        if not json_match:
            logging.error(f"Comparator did not return JSON. Raw output:\n{output}")
            data = {}
        else:
            json_str = json_match.group(1)
            logging.info(f"json json_str for node is: {json_str}")
            try:
                data = json.loads(json_str)
                logging.info(f"json output for node is: {data}")
            except json.JSONDecodeError as e:
                logging.error(f"Failed to decode JSON: {e}\nRaw JSON string:\n{json_str}")
                data = {}
                logging.info(data)

    except subprocess.CalledProcessError as e:
        logging.exception(f"Error running comparator: {e}")
