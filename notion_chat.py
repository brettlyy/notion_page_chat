import os
import json
import uuid
from dotenv import load_dotenv

from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import DirectoryLoader
from langchain_chroma import Chroma
from langchain_classic.chains import RetrievalQA
from langchain_core.documents import Document
from langchain_community.chat_message_histories.in_memory import ChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory

import chainlit as cl

##########################
# Variables
##########################
load_dotenv()
openai_token = os.getenv('OPENAI_API_KEY')

data_dir = './data/docs/'
chroma_dir = './../data/chroma_db'  # persistent Chroma store
file_tracker_path = os.path.join(chroma_dir, "file_tracker.json")

text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=0)
bot_name = "Notion Assistant"

##########################
# Helper: track processed files for incremental load
##########################
def load_file_tracker():
    if os.path.exists(file_tracker_path):
        with open(file_tracker_path, "r") as f:
            return json.load(f)
    return {}

def save_file_tracker(tracker):
    os.makedirs(chroma_dir, exist_ok=True)
    with open(file_tracker_path, "w") as f:
        json.dump(tracker, f)

##########################
# Build / load Chroma vector store incrementally
##########################
embeddings = OpenAIEmbeddings(
    model="text-embedding-3-small",
    openai_api_key=openai_token
)
docsearch = None
file_tracker = load_file_tracker()

# Load existing Chroma if it exists
if os.path.exists(chroma_dir) and os.listdir(chroma_dir):
    print("Loading existing Chroma vector store...")
    docsearch = Chroma(
        persist_directory=chroma_dir,
        embedding_function=embeddings
    )
else:
    os.makedirs(chroma_dir, exist_ok=True)

# Load all documents from data dir
loader = DirectoryLoader(data_dir, glob="*.txt")
docs = loader.load()

texts_to_add = []
metadatas_to_add = []
ids_to_add = []

for doc in docs:
    file_path = doc.metadata["source"]  # DirectoryLoader sets 'source' to file path
    file_mod_time = os.path.getmtime(file_path)

    # Only process if new or updated
    if file_path not in file_tracker or file_tracker[file_path] < file_mod_time:
        chunks = text_splitter.split_text(doc.page_content)
        texts_to_add.extend(chunks)
        metadatas_to_add.extend([{"source": os.path.basename(file_path)} for _ in chunks])
        ids_to_add.extend([str(uuid.uuid5(uuid.NAMESPACE_DNS, os.path.basename(file_path) + str(i)))
                           for i in range(len(chunks))])
        file_tracker[file_path] = file_mod_time

# Add new texts to Chroma
if texts_to_add:
    if docsearch is None:
        print("Building new Chroma vector store from documents...")
        docsearch = Chroma.from_texts(
            texts_to_add,
            embeddings,
            metadatas=metadatas_to_add,
            ids=ids_to_add,
            persist_directory=chroma_dir
        )
    else:
        print(f"Adding {len(texts_to_add)} new chunks to Chroma store...")
        docsearch.add_texts(texts_to_add, metadatas=metadatas_to_add, ids=ids_to_add)
        docsearch.persist()
    save_file_tracker(file_tracker)
    print("Chroma store updated and file tracker saved.")
else:
    print("No new documents to add. Using existing Chroma store.")

##########################
# Chainlit: rename bot
##########################
@cl.author_rename
def rename(orig_author: str):
    rename_dict = {"Chatbot": bot_name}
    return rename_dict.get(orig_author, orig_author)

##########################
# Chainlit: chat start
##########################
# Session-based in-memory chat histories
session_histories = {}

def get_history(session_id: str):
    if session_id not in session_histories:
        session_histories[session_id] = ChatMessageHistory()
    return session_histories[session_id]

@cl.on_chat_start
async def on_chat_start():
    # Build your RetrievalQA chain (classic)
    base_chain = RetrievalQA.from_chain_type(
        llm=ChatOpenAI(model_name="gpt-3.5-turbo", temperature=0, streaming=True),
        chain_type="stuff",
        retriever=docsearch.as_retriever(),
        return_source_documents=True,
    )

    # Wrap it with RunnableWithMessageHistory to handle per-session chat history
    chain = RunnableWithMessageHistory(
        base_chain,
        get_session_history=get_history,
        input_messages_key="question",    # key for user input in the chain
        history_messages_key="chat_history"  # key where chat history will be injected
    )

    cl.user_session.set("chain", chain)

##########################
# Chainlit: message handler
##########################
@cl.on_message
async def main(message: cl.Message):
    chain: RunnableWithMessageHistory = cl.user_session.get("chain")
    cb = cl.AsyncLangchainCallbackHandler()

    # Use the Chainlit session ID to fetch the correct history
    session_id = cl.user_session.get_id()
    res = await chain.invoke(
        {"question": message.content},
        config={"configurable": {"session_id": session_id}},
        callbacks=[cb]
    )

    answer = res["answer"]
    source_documents = res.get("source_documents", [])

    text_elements = []
    if source_documents:
        for idx, source_doc in enumerate(source_documents):
            source_name = f"source_{idx}"
            text_elements.append(
                cl.Text(content=source_doc.page_content, name=source_name)
            )
        source_names = [text_el.name for text_el in text_elements]
        if source_names:
            answer += f"\nSources: {', '.join(source_names)}"
        else:
            answer += "\nNo sources found"

    await cl.Message(content=answer, elements=text_elements).send()
