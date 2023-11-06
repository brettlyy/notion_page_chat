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
        #SETUP API VARIABLES
###############################

load_dotenv()
api_token = os.getenv('NOTION_TOKEN')

notion_request_headers = {
    "Authorization": f"Bearer {api_token}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

project_url = 'https://api.notion.com/v1/search'

################################
        #PULL PAGE IDs
################################

def get_page_ids(url, header=notion_request_headers):
    search_params = {"filter": {"value": "page", "property": "object"}}
    page_search_response = requests.post(
        url, json=search_params, headers=header)

    page_search = page_search_response.json()

    pages = page_search['results']

    return pages

#################################
        #SETUP DOCUMENTS
#################################

def get_document_data(page_ids):
    structured_document_list = []

    for page in page_ids:
        #skip if database
        if page['parent']['type'] == 'database_id':
            continue

        #save metadata
        page_id = page['id']
        try: #titles come in different formats, so hopefully this will make it work!
            page_title = page['properties']['title']['title'][0]['plain_text']
        except KeyError:
            page_title = page['properties']['']['title'][0]['plain_text']

        page_created_date = page['created_time']
        page_created_by_id = page['created_by']['id']
        page_last_update_date = page['last_edited_time']
        page_last_update_by_id = page['last_edited_by']['id']

        #pull blocks from each page
        blocks_url = f'https://api.notion.com/v1/blocks/{page_id}/children'
        blocks_response = requests.get(blocks_url, headers=notion_request_headers)
        blocks = blocks_response.json()

        #drill into block content, add to list, and combine
        block_content_list = []

        #setup variables to support breakout of bullet and numbered lists
        n = 1 #for counting up numbered lists
        previous_block = '' #to compare to previous block to know when to start over count
        for block in blocks['results']:
            #save block type and content
            try:
                block_type = block['type']
            except IndexError:
                block_type = ''

            #skip if block_type one of the types that doesn't produce clean text content
            if block_type in ['table','divider','column_list','child_page','image','child_database','']:
                continue

            #loop through annotations within block content of the types we want
            block_annotation_list = []
            for i in block[block_type]['rich_text']:
                try:
                    content_item = i['plain_text']
                    block_annotation_list.append(content_item)
                except KeyError:
                    pass
            
            #add bullets and numbers if applicable, if not just use the content
            if block_type == 'bulleted_list_item':    
                content = '\n-'+''.join(block_annotation_list) #combine seperated annotations
                previous_block = block_type #save off previous block to increment number in ordered fash
            elif block_type == 'numbered_list_item':
                if previous_block != 'numbered_list_item':
                    n=1 #set n back to 1
                    content = '\n'+str(n)+'.'+''.join(block_annotation_list) #combine seperated annotations
                    previous_block = block_type #save off previous block to increment number in ordered fashion
                    n += 1 #increment number
                else:
                    content = '\n'+str(n)+'.'+''.join(block_annotation_list) #combine seperated annotations
                    previous_block = block_type #save off previous block to increment number in ordered fashion
                    n += 1 #increment number
            else:
                content = ''.join(block_annotation_list) #combine seperated annotations
                previous_block = block_type #save off previous block to increment number in ordered fash

            block_content_list.append(content) #append the combined items to list
            page_content = {
                'page_id': page_id,
                'page_title': page_title,
                'page_created_date': page_created_date,
                'page_created_by_id': page_created_by_id,
                'page_last_update_date': page_last_update_date,
                'page_last_update_by_id': page_last_update_by_id,
                'content': ' '.join(block_content_list) #save content as one big combined block
            }

        structured_document_list.append(page_content)
    return structured_document_list

#################################
        #SAVE AS TEXT
#################################

def save_to_txt(list, filepath):
    """Take our notion data and build it into txt files with the page title as the name."""
    #write to file
    for doc in list:
        title = doc['page_title']
        filename = doc['page_title'].replace(" ","").replace("&","and").replace("#","").replace("/","_") #remove chars that don't work in titles
        created_date = doc['page_created_date']
        last_edit_date = doc['page_last_update_date']
        content = doc['content']
        text_file = f'Title: {title}\nCreated On: {created_date}\n\n{content}'
        with open(f'{filepath}{filename}.txt', 'w') as f:
            f.write(text_file)

    print(f'Data successfully saved to {filepath}')

#################################
        #SETUP DOCS
#################################

if __name__ == '__main__':
    pages = get_page_ids(project_url)
    pages_list = get_document_data(pages)
    save_to_txt(pages_list, './../data/')