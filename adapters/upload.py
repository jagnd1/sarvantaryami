
import os
import tempfile
import asyncio
from typing import List
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import (
    TextLoader, PyPDFLoader, UnstructuredWordDocumentLoader, UnstructuredExcelLoader
)
from langchain_core.runnables import Runnable
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from fastapi import UploadFile, File

from adapters.agents.rag_agent import qdrant_vectorstore, llm
from adapters.agents.api_agent import intent_vectorstore

SUPPORTED_LOADERS = {
    ".pdf": PyPDFLoader,
    ".txt": TextLoader,
    ".md": TextLoader,
    ".docx": UnstructuredWordDocumentLoader,
    ".xlsx": UnstructuredExcelLoader
}


generate_prompt = PromptTemplate.from_template(
    """Given the following technical document text, generate 3-5 realistic user queries that an assistant might be asked based on it.

    TEXT:
    ---
    {text}
    ---

    Queries (one per line):
    """
)
generate_chain = generate_prompt | llm | StrOutputParser()
import logging
logger = logging.getLogger(__name__)

async def generate_intent_queries_from_text(text: str) -> list[str]:
    try:
        result = await generate_chain.ainvoke({"text": text})
        return [line.strip() for line in result.strip().split("\n") if line.strip()]
    except Exception as e:
        logger.error(f"intent gen error: {e}")
        return []

def load_and_split(filename: str, file_bytes: bytes) -> List[Document]:
    ext = os.path.splitext(filename)[1].lower()
    if ext not in SUPPORTED_LOADERS:
        raise ValueError(f"unsupported file type: {ext}, allowed: {list(SUPPORTED_LOADERS.keys())}")
    
    temp_file_path = None
    try: 
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_file:
            temp_file.write(file_bytes)
            temp_file_path = temp_file.name
        
        loader = SUPPORTED_LOADERS[ext](temp_file_path)
        docs = loader.load()
    except Exception as e:
        raise RuntimeError(f"failed to load doc: {e}")
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)    
    
    # split
    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        separators=["\n\n", "\n", ".", " "],  # paragraph > sentence > word
        chunk_size=600, chunk_overlap=50)
    return splitter.split_documents(docs)

async def _upload_doc(filename: str, file_bytes: bytes, generate_intents: bool = True) -> List[Document]:
    loop = asyncio.get_running_loop()
    
    # Run blocking loader/splitter in thread pool
    chunks = await loop.run_in_executor(None, load_and_split, filename, file_bytes)
    
    for c in chunks:
        c.metadata["route"] = "rag_chain"    
    
    # Add to vectorstore (blocking)
    await loop.run_in_executor(None, qdrant_vectorstore.add_documents, chunks)
    
    if generate_intents and chunks:
        # only generate for the first chunk to be fast (local llm bottleneck)
        queries = await generate_intent_queries_from_text(chunks[0].page_content)
        
        new_intents = []
        for q in queries:
            if q:
                new_intents.append(Document(page_content=q, metadata={"id": "rag_chain"}))
        
        if new_intents:
            await loop.run_in_executor(None, intent_vectorstore.add_documents, new_intents)
        
    return chunks
