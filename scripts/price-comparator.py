import json
import glob
import sys
import logging
import textwrap
import os
import argparse

# ---------------- Logger ----------------
def setup_logger(name="product_comparator", parent_logger=None, log_file=None, log_level=logging.DEBUG):
    if parent_logger:
        logger = parent_logger.getChild(name)
    else:
        logger = logging.getLogger(name)
        if not logger.handlers:
            console_handler = logging.StreamHandler(sys.stderr)
            console_handler.setFormatter(logging.Formatter('[%(levelname)s] %(name)s: %(message)s'))
            console_handler.setLevel(log_level)
            logger.addHandler(console_handler)

            logger.setLevel(log_level)

    return logger


logger = None


# ---------------- Load JSON files ----------------
def load_json_files(file_paths, min_relevance=70):
    """
    Load JSON files, combine all products, and filter by relevance.
    """
    all_products_combined = []
    logger.debug(f"Loading JSON files: {file_paths} with min_relevance={min_relevance}")

    for file_path in file_paths:
        store_name = file_path.replace(".json", "").replace("results_", "").title()
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                products = json.load(f)
                logger.debug(f"Loaded {len(products)} products from {file_path} (store={store_name})")

                for product in products:
                    relevance = product.get("relevance", product.get("relevance_score", 0))
                    try:
                        relevance_score = float(relevance) if relevance else 0
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid relevance score '{relevance}' for product: {product.get('item_name', 'Unknown')}")
                        relevance_score = 0

                    if relevance_score >= min_relevance:
                        product["store"] = store_name
                        product["original_relevance"] = relevance_score
                        all_products_combined.append(product)

        except Exception as e:
            logger.error(f"Failed to load {file_path}: {e}")

    logger.info(f"Total combined products after filtering: {len(all_products_combined)}")
    return all_products_combined


# ---------------- Create formatted table (optional) ----------------
def create_formatted_table(user_input, products, filename="comparison.txt"):
    logger.debug(f"Creating formatted table with {len(products)} items")
    col_widths = {
        'item': 35,
        'store': 12,
        'brand': 15,
        'packing': 15,
        'item_name': 50,
        'price': 10,
        'relevance': 10
    }

    sep_line = "-" * (sum(col_widths.values()) + 18)
    table_lines = []
    header = f"{'Item':<{col_widths['item']}} | {'Store':<{col_widths['store']}} | {'Brand':<{col_widths['brand']}} | {'Packing':<{col_widths['packing']}} | {'Item Name':<{col_widths['item_name']}} | {'Price':<{col_widths['price']}} | {'Relevance':<{col_widths['relevance']}}"
    table_lines.append(header)
    table_lines.append(sep_line)

    def wrap_text(text, width):
        return textwrap.wrap(text, width=width) or [""]

    first_row = True
    for prod in products:
        item_wrapped = wrap_text(prod.get('item_name', ''), col_widths['item_name'])
        for i, line in enumerate(item_wrapped):
            item_col = user_input if first_row and i == 0 else ""
            store_col = prod.get('store', '') if i == 0 else ""
            brand_col = prod.get('brand', '') if i == 0 else ""
            packing_col = prod.get('packing', '') if i == 0 else ""
            price_col = prod.get('price', '') if i == 0 else ""
            relevance_col = str(prod.get('original_relevance', 0)) if i == 0 else ""

            table_lines.append(f"{item_col:<{col_widths['item']}} | {store_col:<{col_widths['store']}} | {brand_col:<{col_widths['brand']}} | {packing_col:<{col_widths['packing']}} | {line:<{col_widths['item_name']}} | {price_col:<{col_widths['price']}} | {relevance_col:<{col_widths['relevance']}}")

        first_row = False

    table_text = "\n".join(table_lines)

    if filename:
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(table_text)
            logger.debug(f"Formatted table saved to '{filename}'")
        except Exception as e:
            logger.error(f"Failed to save formatted table to '{filename}': {e}")

    return table_text


# ---------------- Process Comparison ----------------
def process_product_comparison(user_input, min_relevance=50, save_formatted_table=False,
                               parent_logger=None, log_file=None, log_level=logging.DEBUG):
    """
    Process product comparison: load, combine, sort by relevance, return top 5.
    """
    global logger
    logger = setup_logger(parent_logger=parent_logger, log_file=log_file, log_level=log_level)

    logger.info(f"Starting product comparison for: '{user_input}'")
    json_files = glob.glob("results_*.json")

    if not json_files:
        return {"error": "No JSON files found", "user_input": user_input, "total_matches": 0, "headers": [], "rows": []}

    all_products = load_json_files(json_files, min_relevance=min_relevance)

    if not all_products:
        return {"message": "No products found above relevance threshold", "user_input": user_input,
                "total_matches": 0, "headers": [], "rows": []}

    # Sort by original relevance descending
    all_products.sort(key=lambda x: -x.get("original_relevance", 0))

    # Keep top 5
    top_products = all_products[:5]

    table_data = {
        "user_input": user_input,
        "total_matches": len(top_products),
        "headers": ["Store", "Brand", "Packing", "Item Name", "Price", "Original Relevance"],
        "rows": []
    }

    for prod in top_products:
        table_data["rows"].append({
            "store": prod.get("store", ""),
            "brand": prod.get("brand", ""),
            "packing": prod.get("packing", ""),
            "item_name": prod.get("item_name", ""),
            "price": prod.get("price", ""),
            "original_relevance": prod.get("original_relevance", 0)
        })

    if save_formatted_table:
        create_formatted_table(user_input, top_products)

    return table_data


# ---------------- Main ----------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Product Comparator Script")
    parser.add_argument("--product", type=str, required=True, help="Product name to search/compare")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode (default: False)")
    args = parser.parse_args()

    user_input = args.product
    headless = args.headless

    log_file = "product_comparator.log"

    if os.path.exists(log_file):
        open(log_file, 'w').close()

    logger = setup_logger(log_file=log_file)
    logger.info("=== Product Comparator Script Started ===")
    logger.info(f"Product input: {user_input}")
    logger.info(f"Headless mode: {headless}")

    result = process_product_comparison(
        user_input,
        min_relevance=20,
        save_formatted_table=True,
        log_file=log_file
    )

    logger.info(f"Comparison completed. Found {result.get('total_matches', 0)} matches")

    try:
        with open("output.json", "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        logger.info("JSON result saved to output.json")
    except Exception as e:
        logger.error(f"Failed to save output.json: {e}")

    logger.info("=== Product Comparator Script Completed ===")
    print(json.dumps(result, indent=2, ensure_ascii=False))
