import requests
import os
import json
import re
import emoji
from collections import Counter
from dotenv import load_dotenv

# Set up the Notion API token and base URL
NOTION_API_KEY = "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"
NOTION_BASE_URL = "https://api.notion.com/v1"
NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}
WORKSPACE_SLUG="gpt4o"
API_BASE_URL="https://allm.ungr.app/api"
API_TOKEN="WMQE92B-BQK4DW7-HQVH9TW-3N8XXFJ"

# Function to clean noisy content (removes emojis and excessive whitespace)
def clean_content(text):
    text = emoji.replace_emoji(text, replace="")  # Remove emojis
    text = re.sub(r'\s+', ' ', text)  # Replace multiple spaces with a single space
    return text.strip()  # Remove leading/trailing spaces

# Function to extract content based on property type
def get_content_from_property(value):
    if not value:
        return ""
    content = ""
    if value['type'] == 'title' and value['title']:
        content = clean_content(value['title'][0].get('text', {}).get('content', ""))
    elif value['type'] == 'rich_text' and value['rich_text']:
        content = clean_content(" ".join(rt.get('text', {}).get('content', "") for rt in value['rich_text']))
    elif value['type'] == 'number':
        content = clean_content(str(value['number']))
    elif value['type'] == 'people':
        content = clean_content(", ".join([person.get("name", "") for person in value['people']]))
    elif value['type'] == 'date' and value.get("date") and value["date"].get("start"):
        content = value["date"]["start"]
    elif value['type'] == 'created_time':
        content = value["created_time"]

    if isinstance(content, list):
        content = ", ".join(map(str, content))

    return content.strip()

# Function to fetch blocks from a page or block
def fetch_blocks(block_id):
    blocks_url = f"{NOTION_BASE_URL}/blocks/{block_id}/children"
    response = requests.get(blocks_url, headers=NOTION_HEADERS)
    if response.status_code != 200:
        return []
    
    blocks = response.json().get("results", [])
    content_array = []

    for block in blocks:
        block_type = block.get("type", "")
        block_content = ""

        # Check if 'rich_text' exists in the block's type data
        if 'rich_text' in block.get(block_type, {}):
            rich_text = block[block_type].get('rich_text', [])
            for text_item in rich_text:
                content_text = text_item.get('text', {}).get('content', '')
                if content_text:
                    block_content += "\n" + content_text  # Add newline before each content_text

        # Recursively fetch sub-blocks if the block has children
        if block.get("has_children", False):
            sub_block_content = fetch_blocks(block["id"])
            block_content += "\n" + sub_block_content  # Add newline before appending sub-block content

        # Append the processed block content
        if block_content.strip():
            content_array.append(clean_content(block_content))
    
    return "\n".join(content_array)  # Return all block contents as a list

# Function to append a database/page entry to urls.json
def append_to_urls_json(name, url):
    urls_file = "urls.json"
    if os.path.exists(urls_file):
        with open(urls_file, "r", encoding="utf-8") as file:
            urls_data = json.load(file)
    else:
        urls_data = []
    urls_data.append({"name": name, "url": url})
    with open(urls_file, "w", encoding="utf-8") as file:
        json.dump(urls_data, file, indent=4, ensure_ascii=False)

# Function to process a database
def process_database(database_id, database_name):
    print(f"\nProcessing database ID: {database_id}, Name: {database_name}")
    notion_url = f"{NOTION_BASE_URL}/databases/{database_id}/query"
    response = requests.post(notion_url, headers=NOTION_HEADERS)

    if response.status_code == 200:
        data = response.json()
        pages = data['results']

        output_dir = "./data"
        os.makedirs(output_dir, exist_ok=True)

        # Append to urls.json
        database_url = f"https://www.notion.so/{database_id.replace('-', '')}"
        append_to_urls_json(database_name, database_url)

        # Format and save the data
        formatted_data = format_database_data(pages)
        file_name = f"{database_name.replace('/', '_')}.txt"

        file_path = os.path.join(output_dir, file_name)
        with open(file_path, "w", encoding="utf-8") as file:
            file.write(formatted_data)
        print(f"Data for database '{database_name}' has been saved to {file_path}")
    else:
        print(f"Failed to fetch data for database {database_id}: {response.status_code}")

def format_database_data(pages):
    # Identify common keys (without ordering)
    common_keys = identify_common_keys(pages)
    formatted_data = []

    # Limit to first 5 pages (or less if there are fewer)
    pages_to_process = pages[:5]  # Max 5 pages for summary
    # Collect the raw data for the first 5 pages (or all if fewer)
    raw_data_entries = []
    descriptions = {}  # To store descriptions for each key

    for page in pages_to_process:
        properties = page.get("properties", {})
        entry = []

        # Gather content for each key
        for key in common_keys:
            value = properties.get(key, {})
            content = get_content_from_property(value)
            if content:
                entry.append(f"{key}: {content}")
                descriptions[key] = content  # Collecting descriptions for each key

        if entry:
            raw_data_entries.append("\n".join(entry))

    llm_summary_prompt = (
        "### Instructions\n"
        "You will analyze the following pages and generate a structured summary. Your output must include the following:\n"
        "1. **Summary:** Provide a concise overview of what these pages are about.\n"
        "2. **Key Order:** Identify the unique keys present in the pages and list them in order of importance (separate with a slash `/`).\n"
        "   - **Relevance:** The importance of a key is determined by its relevance to the main theme or purpose of the content.\n"
        "3. **Descriptions:** Provide a description for each unique key found in the pages. Each description must explain the significance and context of the key, without including specific data values.\n"
        "   - **Time-related Keys:** For any key that involves time or date, include the following format in the description:\n"
        "     - If the key contains only a date, format it as 'YYYY-MM-DD' (e.g., '2024-11-27').\n"
        "     - If the key contains both a date and time, format it as 'YYYY-MM-DD HH:MM' (e.g., '2024-11-27 15:30').\n"
        "     - If the date has already been provided in 'YYYY-MM-DD' format elsewhere, only show the time in 'HH:MM' format (e.g., '15:30').\n\n"
        "### Additional Guidelines\n"
        "- **Key Structure:** Each page will have exactly the same set of keys. Identify these unique keys and describe them once under the descriptions section.\n"
        "- **Key Format:** Identify the keys exactly as provided in the input and do not modify their names.\n"
        "- **Translation:** Translate any Chinese characters into English across the entire output, including the summary, key order, and descriptions.\n\n"
        "### Expected Output Format\n"
        "Return the result using the following format:\n"
        "Summary: <summary>\n"
        "Key order: <key1> / <key2> / <key3> / <keyN>\n"
        "Descriptions:\n"
        "- <key1>: <description>\n"
        "- <key2>: <description>\n"
        "- <key3>: <description>\n"
        "- <keyN>: <description>\n\n"
        "### Pages to Analyze\n"
        f"{'\n\n'.join(raw_data_entries)}\n\n"
    )



    llm_response = get_llm_response(llm_summary_prompt)
    
    # Extract the ordered keys and descriptions from the LLM response
    summary, key_order, descriptions_from_llm = parse_llm_response(llm_response)
    # Prepare the summary and descriptions to add to the top of the file
    summary_section = f"Summary: {summary}\n"
    descriptions_prompt = "\n".join([f"{key}: {desc}" for key, desc in descriptions_from_llm.items()])
    descriptions_section = "Key Descriptions:\n" + descriptions_prompt
    key_order = [key for key in key_order.split(' / ')]
    contents =[]
    # Now process all pages (with the keys in the order returned by the LLM)
    for page in pages:
        properties = page.get("properties", {})
        entry = []
        skip_entry = False  # Flag to determine if the entry should be skipped
        # Reorder keys according to LLM's response and add content
        for key in key_order:
            value = properties.get(key, {})
            content = get_content_from_property(value)
            if not content:  # If any key's content is missing, skip this entry
                skip_entry = True
                break
            entry.append(f"{key}: {content}")

        if skip_entry:
            continue  # Skip this entry if any key content is missing

        # Fetch block content and append as the last key
        page_id = page["id"]
        block_content = fetch_blocks(page_id)
        
        contents.append(clean_content(block_content))
        # Append the entry to formatted_data only if it's complete
        formatted_data.append("\n".join(entry))
    
    cleaned_data = clean_with_description(formatted_data, descriptions_prompt)

    cleaned_data_file = "./cleaned_data_output.txt"
    contents_file = "./contents_output.txt"

    # Write cleaned_data to the first file
    with open(cleaned_data_file, "w", encoding="utf-8") as f_cleaned:
        f_cleaned.write("\n\n".join(cleaned_data))  # Join each element with \n\n

    # Write contents to the second file
    with open(contents_file, "w", encoding="utf-8") as f_contents:
        f_contents.write("\n\n".join(contents))  # Join each element with \n\n

    for i, content in enumerate(contents):
        if not content.strip():  # Check if content is empty or contains only whitespace
            continue  # Skip this iteration if content is empty
        cleaned_data[i] += f"\nContent: {content}"
        
    # Use clean_with_description to clean the entire formatted data using the LLM descriptions
    whole_content = "\n\n".join(cleaned_data)
    # Add summary and key descriptions at the top
    return summary_section + "\n" + descriptions_section + "\n\n" + whole_content


def get_llm_response(prompt):
    chat_url = f"{API_BASE_URL}/v1/workspace/{WORKSPACE_SLUG}/chat"
    headers = {
        "Authorization": f"Bearer WMQE92B-BQK4DW7-HQVH9TW-3N8XXFJ",
        "Content-Type": "application/json"
    }
    payload = {"message": prompt, "mode": "chat", "sessionId": "unique-session-id"}

    try:
        response = requests.post(chat_url, headers=headers, json=payload)
        if response.status_code == 200:
            response_json = response.json()
            return response_json.get("textResponse", "")
        else:
            return f"Failed to connect. Status code: {response.status_code}"
    except requests.RequestException as e:
        return f"Error: {e}"

def parse_llm_response(response):
    """Parse the LLM response to extract summary, key order, and descriptions"""
    # Assuming the response format is like:
    # Summary: <summary_text>
    # Key order: <key1> / <key2> / <key3>
    # Descriptions: <key1>: <desc1> / <key2>: <desc2> / <key3>: <desc3>
    summary = ""
    key_order = ""
    descriptions = {}

    # Parse the response
    summary_match = re.search(r"Summary:\s*(.*?)(?=\n|Key order:)", response, re.S)
    if summary_match:
        summary = summary_match.group(1).strip()

    key_order_match = re.search(r"Key order:\s*(.*?)(?=\n|Descriptions:)", response, re.S)
    if key_order_match:
        key_order = key_order_match.group(1).strip()

    descriptions_match = re.search(r"Descriptions:\s*(.*)", response, re.S)
    if descriptions_match:
        descriptions_str = descriptions_match.group(1).strip()
        descriptions = {key: desc for key, desc in (item.split(": ", 1) for item in descriptions_str.split("\n") if item)}

    return summary, key_order, descriptions


def clean_with_description(content_list, descriptions):
    """
    Function to clean content using the provided key descriptions and ensure output starts strictly with 'Content: ...'.
    This function processes content in chunks to avoid exceeding the token limit.
    """
    # Calculate the approximate maximum tokens per chunk
    MAX_TOKENS = 500  # Define the token buffer limit (1000 tokens)
    TOKENS_PER_CHARACTER = 0.25  # Approximate average: 1 token ~ 4 characters (in English)
    MAX_CHARACTERS = MAX_TOKENS / TOKENS_PER_CHARACTER  # Max characters that can fit within token buffer

    # Initialize variables
    all_cleaned_content = []  # This will store the final cleaned content after processing chunks
    current_chunk = []  # This will hold the current chunk of content to process
    current_chunk_length = 0  # Current total length of the content in characters

    # Iterate through the content list and process in chunks
    for entry in content_list:
        # Estimate the length of the entry (in characters)
        entry_length = len(entry)

        # Check if adding this entry exceeds the max allowed character count
        if current_chunk_length + entry_length > MAX_CHARACTERS:
            # Process the current chunk if it's full
            if current_chunk:
                # Prepare the prompt for the current chunk
                prompt = create_prompt_for_chunk(current_chunk, descriptions)
                cleaned_content = get_llm_response(prompt)
                content_elements = extract_cleaned_content(cleaned_content)
                all_cleaned_content.extend(content_elements)

            # Reset the chunk and start a new one
            current_chunk = [entry]
            current_chunk_length = entry_length
        else:
            # Add the entry to the current chunk and update the length
            current_chunk.append(entry)
            current_chunk_length += entry_length

    # After processing all entries, make sure the last chunk is processed
    if current_chunk:
        prompt = create_prompt_for_chunk(current_chunk, descriptions)
        cleaned_content = get_llm_response(prompt)
        content_elements = extract_cleaned_content(cleaned_content)
        all_cleaned_content.extend(content_elements)
    
    return all_cleaned_content


def create_prompt_for_chunk(content_chunk, descriptions):
    """
    Helper function to create the LLM prompt for a given chunk of content.
    """
    prompt = (
        "### Instructions\n"
        "Translate all keys' values into English and refine them based on the provided key descriptions.\n"
        "Ensure all records, indexed as 'Record {i}:' in the input, are preserved exactly in the same order and count.\n"
        "The output must start directly with 'Record 1:' and include all records without skipping.\n\n"
        f"<Key Descriptions>\n{descriptions}\n\n"
        f"<Content>\n" + "\n\n".join([f"Record {i+1}:\n{entry}" for i, entry in enumerate(content_chunk)]) + "\n\n"
    )
    return prompt


def extract_cleaned_content(response):
    """
    Helper function to extract the cleaned content from the LLM response.
    Splits the output by records and removes the index line from each record.
    """
    # Split the response by double newlines to separate records
    records = response.strip().split("\n\n")
    # Remove the first line (index line) for each record and return a cleaned list
    cleaned_records = ["\n".join(record.split("\n")[1:]).strip() for record in records if record.strip()]
    
    return cleaned_records

# Function to identify common keys dynamically from the database
def identify_common_keys(pages):
    key_counts = Counter()
    total_pages = len(pages)

    for page in pages:
        properties = page.get("properties", {})
        for key, value in properties.items():
            content = get_content_from_property(value)
            if content:
                key_counts[key] += 1
    # Select keys that appear in more than 50% of the pages with non-empty content
    common_keys = {key for key, count in key_counts.items() if count > total_pages * 0.5}
    return common_keys  # Return the set of common keys without any reordering

# Function to fetch chat response (provided function modified to accept message directly)
def get_chat_response(message):
    chat_url = f"{API_BASE_URL}/v1/workspace/{WORKSPACE_SLUG}/chat"
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {"message": message, "mode": "chat", "sessionId": "unique-session-id"}

    try:
        response = requests.post(chat_url, headers=headers, json=payload)
        if response.status_code == 200:
            response_json = response.json()
            if response_json.get("error") is not None:
                return f"Error: {response_json['error']}"
            return response_json.get("textResponse", "No response text available")
        else:
            return f"Failed to connect. Status code: {response.status_code}"
    except requests.RequestException as e:
        return f"Error: {e}"

#TARGET_DATABASE_NAME = "Blog post"
# Function to fetch databases
def fetch_databases():
    print("\nFetching databases...")
    response = requests.post(f"{NOTION_BASE_URL}/search", headers=NOTION_HEADERS, json={
        "filter": {"property": "object", "value": "database"}
    })

    if response.status_code == 200:
        databases = response.json().get('results', [])
        for db in databases:
            database_id = db['id']
            database_name = db['title'][0]['text']['content'] if db['title'] else "Untitled_Database"
            #if database_name == TARGET_DATABASE_NAME:
            process_database(database_id, database_name)
    else:
        print(f"Failed to fetch databases: {response.status_code}")

# Function to process non-database pages
def fetch_non_database_pages():
    print("\nFetching non-database pages...")
    response = requests.post(f"{NOTION_BASE_URL}/search", headers=NOTION_HEADERS, json={
        "filter": {"property": "object", "value": "page"}
    })

    if response.status_code == 200:
        pages = response.json().get("results", [])
        non_database_pages = [page for page in pages if page['parent']['type'] != 'database_id']

        output_dir = "./data"
        os.makedirs(output_dir, exist_ok=True)

        for page in non_database_pages:
            page_id = page['id']
            page_title = page.get("properties", {}).get("title", {}).get("title", [{}])[0].get("text", {}).get("content", "Untitled")
            block_content = fetch_blocks(page_id)

            # Save page content to a text file
            file_name = f"{clean_content(page_title)}.txt"
            file_path = os.path.join(output_dir, file_name)
            with open(file_path, "w", encoding="utf-8") as file:
                file.write(f"Title: {page_title}\n\n")
                file.write(block_content if block_content else "No content available.")

            # Append to urls.json
            page_url = f"https://www.notion.so/{page_id.replace('-', '')}"
            append_to_urls_json(page_title, page_url)

            print(f"Non-database page '{page_title}' saved to {file_path}")
    else:
        print(f"Failed to fetch non-database pages: {response.status_code}")

def fetch_all_data():
    fetch_databases()
    #fetch_non_database_pages()

# Run the main function
if __name__ == "__main__":
    fetch_all_data()
