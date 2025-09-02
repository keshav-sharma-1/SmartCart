from polyfuzz import PolyFuzz

def compute_relevance(search_input, brand, item_name, packing, logger=None):
    logger.info(f"input - '{search_input}', brand - '{brand}', item_name -  {item_name}, packing - {packing}")
    # Combine brand, item name, and packing into one product description
    product_description = f"{brand} {item_name} {packing}".strip()
    logger.info(f"calculating Relevance score between '{search_input}' and '{product_description}'")
    

    # Wrap both as lists for PolyFuzz
    search_input_list = [search_input]
    product_list = [product_description]

    # Run fuzzy matching
    model = PolyFuzz("TF-IDF")
    model.match(search_input_list, product_list)

    # Extract similarity score and convert to percentage
    score = model.get_matches()["Similarity"].iloc[0]
    percentage = round(score * 100, 2)


    logger.info(f"Relevance score between '{search_input}' and '{product_description}': {percentage}%")

    return percentage

