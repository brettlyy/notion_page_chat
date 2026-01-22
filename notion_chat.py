import os
import json
import uuid
from dotenv import load_dotenv

from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import DirectoryLoader
from langchain_chroma import Chroma
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_community.chat_message_histories.in_memory import ChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.messages import HumanMessage, AIMessage

import chainlit as cl

##########################
# Variables
##########################
load_dotenv()
openai_token = os.getenv('OPENAI_API_KEY')

data_dir = './data/docs/'
chroma_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), './data/chroma_db'))
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

def format_source_snippet(doc, max_chars=300):
    text = doc.page_content.strip().replace("\n", " ")
    if len(text) > max_chars:
        text = text[:max_chars] + "..."
    return text

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

# Parse metadata from file headers
def parse_metadata_from_content(doc):
    """Extract metadata from --- header if present"""
    content = doc.page_content
    metadata = doc.metadata.copy()
    
    if content.startswith("---"):
        # Find the end of the metadata block
        end_idx = content.find("---", 3)
        if end_idx != -1:
            metadata_block = content[3:end_idx].strip()
            # Parse key: value pairs
            for line in metadata_block.split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    metadata[key.strip()] = value.strip()
            # Remove metadata from content
            doc.page_content = content[end_idx + 3:].strip()
    
    doc.metadata = metadata
    return doc

docs = [parse_metadata_from_content(doc) for doc in docs]

texts_to_add = []
metadatas_to_add = []
ids_to_add = []

for doc in docs:
    file_path = doc.metadata["source"]
    file_mod_time = os.path.getmtime(file_path)

    # Only process if new or updated
    if file_path not in file_tracker or file_tracker[file_path] < file_mod_time:
        chunks = text_splitter.split_text(doc.page_content)
        
        # Extract metadata from original doc (notion_url, notion_id, etc.)
        metadata_base = {
            "source": os.path.basename(file_path),
            "file_path": file_path
        }
        
        # Copy over any additional metadata from the original document
        for key in ["notion_url", "notion_id", "title", "url"]:
            if key in doc.metadata:
                metadata_base[key] = doc.metadata[key]
        
        texts_to_add.extend(chunks)
        metadatas_to_add.extend([metadata_base.copy() for _ in chunks])
        ids_to_add.extend([
            str(
                uuid.uuid5(
                    uuid.NAMESPACE_DNS,
                    f"{file_path}:{i}"
                )
            )
            for i in range(len(chunks))
        ])
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
    llm = ChatOpenAI(
        model_name="gpt-4o-mini",
        temperature=0
    )

    if docsearch is None:
        await cl.Message(
            content="Document index is not ready. Please refresh in a moment."
        ).send()
        return

    retriever = docsearch.as_retriever(search_kwargs={"k": 4})

    print(f"Chroma loaded with {docsearch._collection.count()} chunks")

    # Store in Chainlit session
    cl.user_session.set("llm", llm)
    cl.user_session.set("retriever", retriever)

##########################
# Chainlit: message handler
##########################
@cl.on_message
async def main(message: cl.Message):
    llm = cl.user_session.get("llm")
    retriever = cl.user_session.get("retriever")
    session_id = cl.user_session.get("id")
    
    # Get chat history
    history = get_history(session_id)
    
    # Retrieve relevant documents
    docs = retriever.invoke(message.content)
    print(f"[DEBUG] Retrieved {len(docs)} docs:",
          [d.metadata.get("source", "unknown") for d in docs])
    
    # Debug: print metadata
    for doc in docs[:1]:  # Just print first doc's metadata
        print(f"[DEBUG] Metadata keys: {doc.metadata.keys()}")
        print(f"[DEBUG] Full metadata: {doc.metadata}")
    
    # Format context from retrieved docs
    context = "\n\n".join(doc.page_content for doc in docs)
    
    # Build the prompt with chat history
    messages = [
        ("system", 
         "You are a helpful assistant. Answer using ONLY the provided context. "
         "If no relevant context is provided, say you do not know.\n\n"
         f"Context:\n{context}")
    ]
    
    # Add chat history
    for msg in history.messages:
        if isinstance(msg, HumanMessage):
            messages.append(("human", msg.content))
        elif isinstance(msg, AIMessage):
            messages.append(("assistant", msg.content))
    
    # Add current question
    messages.append(("human", message.content))
    
    # Create prompt and invoke WITHOUT streaming callback
    prompt = ChatPromptTemplate.from_messages(messages)
    chain = prompt | llm | StrOutputParser()
    
    answer = await chain.ainvoke({})
    
    # Update chat history
    history.add_message(HumanMessage(content=message.content))
    history.add_message(AIMessage(content=answer))
    
    # Format sources with clickable links
    sources_list = []
    sources_seen = set()
    
    if docs:
        for source_doc in docs:
            source_name = source_doc.metadata.get('source', 'document')
            
            # Skip duplicate sources
            if source_name in sources_seen:
                continue
            sources_seen.add(source_name)
            
            # Get Notion URL from metadata
            notion_url = source_doc.metadata.get('notion_url')
            title = source_doc.metadata.get('title', source_name)
            
            print(f"[DEBUG] Source: {source_name}, URL: {notion_url}")
            
            if notion_url:
                # Create markdown link
                sources_list.append(f"- [{title}]({notion_url})")
            else:
                # Fallback to just the name
                sources_list.append(f"- {source_name}")
        
        if sources_list:
            answer += "\n\n**Sources:**\n" + "\n".join(sources_list)

    await cl.Message(content=answer).send()