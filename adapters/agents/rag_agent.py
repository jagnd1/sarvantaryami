# services/rag_agent.py
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams
from langchain_ollama import OllamaEmbeddings
from langchain_qdrant import QdrantVectorStore
from langchain.chains.retrieval_qa.base import RetrievalQA
from adapters.agents.sql_agent import llm
from langchain_core.documents import Document

# embeddings
embeddings = OllamaEmbeddings(model="mistral")

# rag tool
qdrant_cli = QdrantClient(host="localhost", port=6333)
# create collection if it doesn't exist
collection_name = "rag_collection"
if collection_name not in [c.name for c in qdrant_cli.get_collections().collections]:
    qdrant_cli.recreate_collection(collection_name=collection_name, 
                                   vectors_config=VectorParams(
                                       size=len(embeddings.embed_query("test")),
                                       distance=Distance.COSINE,),)
# load vector store
qdrant_vectorstore = QdrantVectorStore(client=qdrant_cli, collection_name="rag_collection", 
                                       embedding=embeddings)
retriever = qdrant_vectorstore.as_retriever()
rag_chain_base = RetrievalQA.from_chain_type(llm=llm, retriever=retriever)

# intent vector setup for main routing
intent_docs = [
    Document(page_content="words like database, table, column", metadata={"id": "sql_agent"}),
    Document(page_content="get account balance from ac table", metadata={"id": "sql_agent"}),
    Document(page_content="fetch customer details where customer_id is 0x...", metadata={"id": "sql_agent"}),
    Document(page_content="list all transactions from wallet table", metadata={"id": "sql_agent"}),
    Document(page_content="retrieve bank details by bank_id", metadata={"id": "sql_agent"}),
    Document(page_content="select fee slabs for a specific partner", metadata={"id": "sql_agent"}),
    Document(page_content="get wallet balance for customer", metadata={"id": "sql_agent"}),
    Document(page_content="show all limits set in limit_control table", metadata={"id": "sql_agent"}),
    Document(page_content="what is the balance in walletprog for id X?", metadata={"id": "sql_agent"}),

    Document(page_content="what is RFC, specification, protocol", metadata={"id": "rag_chain"}),
    Document(page_content="what is SCEP protocol?", metadata={"id": "rag_chain"}),
    Document(page_content="explain Simple Certificate Enrollment Protocol", metadata={"id": "rag_chain"}),
    Document(page_content="how does PKI certificate enrolment work?", metadata={"id": "rag_chain"}),
    Document(page_content="RFC 8894 specification summary", metadata={"id": "rag_chain"}),
    Document(page_content="what does the SCEP RFC define?", metadata={"id": "rag_chain"}),
    Document(page_content="describe certificate enrollment protocol used by routers", metadata={"id": "rag_chain"}),
    Document(page_content="what is nexo FAST protocol?", metadata={"id": "rag_chain"}),
    Document(page_content="what is nexo IS Scope?", metadata={"id": "rag_chain"}),
    Document(page_content="what is nexo TMS protocol?", metadata={"id": "rag_chain"}),

    Document(page_content="hello", metadata={"id": "default_llm"}),
    Document(page_content="who are you?", metadata={"id": "default_llm"}),
    Document(page_content="what can you do?", metadata={"id": "default_llm"}),
    Document(page_content="tell me a joke", metadata={"id": "default_llm"}),
    Document(page_content="thank you", metadata={"id": "default_llm"}),
]
