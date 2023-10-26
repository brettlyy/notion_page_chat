import os
import sys
from dotenv import load_dotenv

import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)

from langchain.document_loaders import TextLoader
from langchain.document_loaders import DirectoryLoader
from langchain.indexes import VectorstoreIndexCreator
from langchain.llms import openai, HuggingFaceHub
#from langchain.chat_models import ChatOpenAI

##########################
    #Variables
##########################
load_dotenv()
#openai_token = os.getenv('OPENAI_API_KEY')
hf_token = os.getenv('hugging_face_token')

data_dir = './../data/'

##########################
    #LLM Setup
##########################
repo_id = 'google/flan-t5-xxl'
llm = HuggingFaceHub(repo_id=repo_id, huggingfacehub_api_token=hf_token, model_kwargs={'temperature': 0.25, 'max_length': 1028})

loader = DirectoryLoader(data_dir, glob="*.txt")
index = VectorstoreIndexCreator().from_loaders([loader])

##########################
    #Document Function
##########################
def ask_doc(index, question, llm):
    print(index.query(question, llm=llm))

if __name__ == '__main__':
    query = sys.argv[1]
    ask_doc(index=index, question=query, llm=llm)
