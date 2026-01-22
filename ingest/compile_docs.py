#file to pull down contents of notion pages to save to documents for lookup

###############################
        #IMPORTS
###############################

import os
import json
import requests
from datetime import datetime, timezone

from dotenv import load_dotenv

###############################
        #SETUP VARIABLES
###############################

load_dotenv()
api_token = os.getenv('NOTION_TOKEN')

notion_request_headers = {
    "Authorization": f"Bearer {api_token}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

project_url = 'https://api.notion.com/v1/search'

doc_directory = './../data/docs/'

# these blocks don't produce clean text, so skip them
blocks_to_skip = ['divider','image','child_database','', 'file']

#################################
# FETCH PAGES
#################################

def get_page_ids():
    page_ids = []

    url = "https://api.notion.com/v1/search"
    start_cursor = None

    while True:
        params = {"filter": {"value": "page", "property": "object"}}
        if start_cursor:
            params["start_cursor"] = start_cursor

        res = requests.post(url, headers=notion_request_headers, json=params).json()
        for page in res.get("results", []):
            page_ids.append(page["id"])

        if not res.get("has_more"):
            break
        start_cursor = res.get("next_cursor")

    print(f"Total pages fetched from workspace: {len(page_ids)}")

    return page_ids


#################################
# FETCH BLOCKS AND EXTRACT TEXT
#################################

def extract_block_text(block):
    block_type = block["type"]
    data = block.get(block_type, {})

    rich_text = data.get("rich_text") or data.get("text")
    if rich_text:
        return "".join(rt.get("plain_text", "") for rt in rich_text)
    return ""

def fetch_blocks_recursively(block_id, headers, visited=None):
    if visited is None:
        visited = set()
    if block_id in visited:
        return []
    visited.add(block_id)

    blocks_url = f"https://api.notion.com/v1/blocks/{block_id}/children"
    all_blocks = []
    start_cursor = None

    while True:
        params = {"start_cursor": start_cursor} if start_cursor else {}
        res = requests.get(blocks_url, headers=headers, params=params).json()

        for block in res.get("results", []):
            # skip child_page; each child page is processed separately
            if block["type"] != "child_page":
                all_blocks.append(block)
            if block.get("has_children") and block["type"] != "child_page":
                all_blocks.extend(fetch_blocks_recursively(block["id"], headers, visited))

        if not res.get("has_more"):
            break
        start_cursor = res.get("next_cursor")

    return all_blocks

def get_document_data(page_id):
    """
    Extract all text from a page by its ID.
    Preserves headings, bulleted/numbered lists, and spacing between blocks.
    Returns a dict with page metadata and content.
    """
    page_url = f"https://api.notion.com/v1/pages/{page_id}"
    page = requests.get(page_url, headers=notion_request_headers).json()

    # Get page title safely
    try:
        page_title = page['properties']['title']['title'][0]['plain_text']
    except (KeyError, IndexError):
        page_title = page['properties'].get('', {}).get('title', [{}])[0].get('plain_text', 'Untitled')

    print(f"Processing page: {page_title} (id: {page_id})")

    # Fetch all blocks recursively
    blocks = fetch_blocks_recursively(page_id, notion_request_headers)

    block_content_list = []
    numbered_count = 1
    previous_block_type = ''

    for block in blocks:
        block_type = block.get("type", "")
        if block_type in blocks_to_skip:
            continue

        text = extract_block_text(block)
        if not text:
            continue

        # Handle headings
        if block_type == "heading_1":
            content = f"# {text}"
        elif block_type == "heading_2":
            content = f"## {text}"
        elif block_type == "heading_3":
            content = f"### {text}"
        # Handle lists
        elif block_type == 'bulleted_list_item':
            content = f"- {text}"
        elif block_type == 'numbered_list_item':
            if previous_block_type != 'numbered_list_item':
                numbered_count = 1
            content = f"{numbered_count}. {text}"
            numbered_count += 1
        # Regular paragraph/text blocks
        else:
            content = text

        previous_block_type = block_type

        # Add extra newline for separation
        block_content_list.append(content + "\n")

    # Combine everything into one document dict
    return {
        'page_id': page_id,
        'page_title': page_title,
        'content': "".join(block_content_list)  # preserves newlines
    }


#################################
# SAVE TXT
#################################

def save_to_txt(docs, filepath):
    for doc in docs:
        filename = doc['page_title'].replace(" ","").replace("&","and").replace("#","").replace("/","_")
        text_file = f"Title: {doc['page_title']}\n\n{doc['content']}"
        with open(f"{filepath}{filename}.txt", "w") as f:
            f.write(text_file)
        print(f"Saved {filename}.txt")

#################################
# MAIN
#################################

if __name__ == "__main__":
    # Get all pages under root
    #page_ids = get_page_ids()

    all_docs = []
    # for page_id in page_ids:
    #     doc = get_document_data(page_id)
    #     all_docs.append(doc)

    doc = get_document_data("2c21cd0c-6137-80df-8018-d3a219ae91b0")
    all_docs.append(doc)

    save_to_txt(all_docs, doc_directory)

