import os
import sys

import uuid
from dotenv import load_dotenv

from langchain.vectorstores import Chroma
from langchain.document_loaders import DirectoryLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter

#from langchain.embeddings.openai import OpenAIEmbeddings



##########################
    #Variables
##########################
load_dotenv()
openai_token = os.getenv('OPENAI_API_KEY')

data_dir = './../data/docs/'

text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)

#embeddings = OpenAIEmbeddings()


##########################
    #Doc Setup
##########################
#load documents 
loader = DirectoryLoader(data_dir, glob="*.txt")
docs = loader.load()

#for each document pulled, loop through it and split the text, saving it to a list
docs_list = []
for doc in docs:
    text = text_splitter.split_text(doc.page_content) #drill into the content to split
    docs_list.append(text)
#now merge these sublists back together
texts = [item for sublist in docs_list for item in sublist]

#create metadata for each chunk to provide a source to pull
metadatas = [{"source": f"{i+1}-pl"} for i in range(len(texts))]

#create unique IDs based on the content to use in our Chroma collection
ids = [str(uuid.uuid5(uuid.NAMESPACE_DNS, str(i))) for i in range(len(texts))]


#create a Chroma vector store
# embeddings = OpenAIEmbeddings()
# docsearch = Chroma.from_texts(
#     texts, embeddings, metadatas=metadatas
# )