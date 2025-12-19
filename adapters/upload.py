# services/upload.py

import os
import tempfile
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
generate_chain: Runnable = generate_prompt | llm | StrOutputParser()

def generate_intent_queries_from_text(text: str) -> list[str]:
    try:
        result = generate_chain.invoke({"text": text})
        return [line.strip() for line in result.strip().split("\n") if line.strip()]
    except Exception as e:
        print(f"intent gen error: {e}")
        return []

async def _upload_doc(filename: str, file_bytes: bytes) -> List[Document]:
    # validate the ext
    ext = os.path.splitext(filename)[1].lower()
    if ext not in SUPPORTED_LOADERS:
        raise ValueError(f"unsupported file type: {ext}, allowed: {list(SUPPORTED_LOADERS.keys())}")
    # save to temp file
    temp_file_path = None
    try: 
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_file:
            temp_file.write(file_bytes)
            temp_file_path = temp_file.name
    # use proper loader
        loader = SUPPORTED_LOADERS[ext](temp_file_path)
        docs = loader.load()
    except Exception as e:
        raise RuntimeError(f"failed to load doc: {e}")
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)    
    # split and ingest
    # splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        separators=["\n\n", "\n", ".", " "],  # paragraph > sentence > word
        chunk_size=600, chunk_overlap=50)
    chunks = splitter.split_documents(docs)
    for c in chunks:
        c.metadata["route"] = "rag_chain"    
    qdrant_vectorstore.add_documents(chunks)
    # generate intent samples
    for chunk in chunks[:5]:
        queries = generate_intent_queries_from_text(chunk.page_content)
        intent_docs = [Document(page_content=q, metadata={"id": "rag_chain"}) for q in queries]
        intent_vectorstore.add_documents(intent_docs)

