import os
import sys
from dotenv import load_dotenv

from typing import Optional

from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.document_loaders import DirectoryLoader
from langchain.vectorstores import Chroma
from langchain.chains import ConversationalRetrievalChain
from langchain.chat_models import ChatOpenAI
from langchain.prompts.chat import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain.docstore.document import Document
from langchain.memory import ChatMessageHistory, ConversationBufferMemory

import chainlit as cl



##########################
    #Variables
##########################

load_dotenv()
openai_token = os.getenv('OPENAI_API_KEY')

data_dir = './../data/'

text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)

#--unhide the bot_name variable and the @cl.author_rename below to change the name of the bot. You can also do this in the config.toml file.
#bot_name = 'Notion Assistant'

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

#create metadata for each chunk
metadatas = [{"source": f"{i+1}-pl"} for i in range(len(texts))]

#create a Chroma vector store
embeddings = OpenAIEmbeddings()
docsearch = Chroma.from_texts(
    texts, embeddings, metadatas=metadatas
)

##########################
    #LLM Setup
##########################

system_template = """Use the following pieces of context to answer the users question.
If you don't know the answer, just say that you don't know, don't try to make up an answer.
ALWAYS return a "SOURCES" part in your answer.
The "SOURCES" part should be a reference to the source of the document from which you got your answer.

And if the user greets with greetings like Hi, hello, How are you, etc reply accordingly as well.

Example of your response should be:

The answer is foo
SOURCES: xyz


Begin!
----------------
{summaries}"""

messages = [
    SystemMessagePromptTemplate.from_template(system_template),
    HumanMessagePromptTemplate.from_template("{question}"),
]
prompt = ChatPromptTemplate.from_messages(messages)
chain_type_kwargs = {"prompt": prompt}

##########################
    #App Setup
##########################

##-->Unhide below to include login (need to setup chainlit cloud), necessary for chat history and feedback
# @cl.password_auth_callback
# def auth_callback(username: str, password: str) -> Optional[cl.AppUser]:
#   # Fetch the user matching username from your database
#   # and compare the hashed password with the value stored in the database
#   if (username, password) == ("admin", "admin"):
#     return cl.AppUser(username="admin", role="ADMIN", provider="credentials")
#   else:
#     return None

##-->Unhide below to change bot name
# @cl.author_rename
# def rename(orig_author: str):
#     rename_dict = {"Chatbot": {bot_name}}
#     return rename_dict.get(orig_author, orig_author)

@cl.on_chat_start
async def on_chat_start():

    message_history = ChatMessageHistory()

    memory = ConversationBufferMemory(
        memory_key="chat_history",
        output_key="answer",
        chat_memory=message_history,
        return_messages=True,
    )

    # Create a chain that uses the Chroma vector store
    chain = ConversationalRetrievalChain.from_llm(
        ChatOpenAI(model_name="gpt-3.5-turbo", temperature=0, streaming=True),
        chain_type="stuff",
        retriever=docsearch.as_retriever(),
        memory=memory,
        return_source_documents=True,
    )

    cl.user_session.set("chain", chain)

@cl.on_message
async def main(message: cl.Message):
    # Your custom logic goes here...
    chain = cl.user_session.get("chain")  # type: ConversationalRetrievalChain
    cb = cl.AsyncLangchainCallbackHandler()

    res = await chain.acall(message.content, callbacks=[cb])
    answer = res["answer"]
    source_documents = res["source_documents"]  # type: List[Document]

    text_elements = []  # type: List[cl.Text]

    if source_documents:
        for source_idx, source_doc in enumerate(source_documents):
            source_name = f"source_{source_idx}"
            # Create the text element referenced in the message
            text_elements.append(
                cl.Text(content=source_doc.page_content, name=source_name)
            )
        source_names = [text_el.name for text_el in text_elements]

        if source_names:
            answer += f"\nSources: {', '.join(source_names)}"
        else:
            answer += "\nNo sources found"
    # Send a response back to the user
    await cl.Message(content=answer, elements=text_elements).send()

