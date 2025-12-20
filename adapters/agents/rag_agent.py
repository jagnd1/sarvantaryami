# services/rag_agent.py
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams
from langchain_ollama import OllamaEmbeddings
from langchain_qdrant import QdrantVectorStore
from langchain.chains.retrieval_qa.base import RetrievalQA
from adapters.agents.sql_agent import llm
from langchain_core.documents import Document

from infrastructure.config import settings

# embeddings - using dedicated embedding model for better performance
embeddings = OllamaEmbeddings(model=settings.EMBEDDING_MODEL, base_url=settings.OLLAMA_BASE_URL)

# rag tool
qdrant_cli = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
# check collection dimensions and recreate if mismatch
collection_name = settings.QDRANT_COLLECTION
expected_size = len(embeddings.embed_query("test"))

# fetch collections
colls = qdrant_cli.get_collections().collections
exists = next((c for c in colls if c.name == collection_name), None)

recreate = False
if not exists:
    recreate = True
else:
    # verify vector size matches model
    info = qdrant_cli.get_collection(collection_name)
    current_size = info.config.params.vectors.size
    if current_size != expected_size:
        print(f"warning: dimension mismatch {current_size} vs {expected_size}, recreating {collection_name}")
        recreate = True

if recreate:
    qdrant_cli.recreate_collection(
        collection_name=collection_name, 
        vectors_config=VectorParams(size=expected_size, distance=Distance.COSINE)
    )
# load vector store
qdrant_vectorstore = QdrantVectorStore(client=qdrant_cli, collection_name=collection_name, 
                                       embedding=embeddings)
retriever = qdrant_vectorstore.as_retriever(search_kwargs={"k": 5})
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
    Document(page_content="insert new record into table", metadata={"id": "sql_agent"}),
    Document(page_content="update status in database", metadata={"id": "sql_agent"}),
    Document(page_content="delete row from table", metadata={"id": "sql_agent"}),
    Document(page_content="count number of users in database", metadata={"id": "sql_agent"}),

    Document(page_content="what is RFC, specification, protocol", metadata={"id": "rag_chain"}),
    Document(page_content="what is SCEP protocol?", metadata={"id": "rag_chain"}),
    Document(page_content="tell me about PG service and its features", metadata={"id": "rag_chain"}),
    Document(page_content="key value propositions and benefits", metadata={"id": "rag_chain"}),
    Document(page_content="system architecture and business overview", metadata={"id": "rag_chain"}),
    Document(page_content="explain Simple Certificate Enrollment Protocol", metadata={"id": "rag_chain"}),
    Document(page_content="how does PKI certificate enrolment work?", metadata={"id": "rag_chain"}),
    Document(page_content="RFC 8894 specification summary", metadata={"id": "rag_chain"}),
    Document(page_content="what does the SCEP RFC define?", metadata={"id": "rag_chain"}),
    Document(page_content="describe certificate enrollment protocol used by routers", metadata={"id": "rag_chain"}),
    Document(page_content="what is nexo FAST protocol?", metadata={"id": "rag_chain"}),
    Document(page_content="what is nexo IS Scope?", metadata={"id": "rag_chain"}),
    Document(page_content="what is nexo TMS protocol?", metadata={"id": "rag_chain"}),
    Document(page_content="how do I use valid nexo implementation?", metadata={"id": "rag_chain"}),
    Document(page_content="tell me about ISO 20022 standards", metadata={"id": "rag_chain"}),

    Document(page_content="call api, endpoint, service, invoke", metadata={"id": "api_agent"}),
    Document(page_content="get currency details for USD", metadata={"id": "api_agent"}),
    Document(page_content="create a new country through the service", metadata={"id": "api_agent"}),
    Document(page_content="update bank status via api", metadata={"id": "api_agent"}),
    Document(page_content="delete account using endpoint", metadata={"id": "api_agent"}),
    Document(page_content="invoke create_role_v1_sys_roles_post", metadata={"id": "api_agent"}),
    Document(page_content="fetch health status of the endpoint", metadata={"id": "api_agent"}),
    Document(page_content="post customer data to system", metadata={"id": "api_agent"}),

    Document(page_content="hello", metadata={"id": "default_llm"}),
    Document(page_content="who are you?", metadata={"id": "default_llm"}),
    Document(page_content="what can you do?", metadata={"id": "default_llm"}),
    Document(page_content="tell me a joke", metadata={"id": "default_llm"}),
    Document(page_content="thank you", metadata={"id": "default_llm"}),
    Document(page_content="what is the weather like?", metadata={"id": "default_llm"}),
    Document(page_content="write a poem", metadata={"id": "default_llm"}),
]
