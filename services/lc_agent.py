# services/lc_agent.py

from langchain_core.runnables import Runnable, RunnableLambda
from langchain.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END
from typing import TypedDict

from services.sql_agent import llm, sql_subgraph
from services.rag_agent import rag_chain_base
from services.api_agent import api_subgraph, intent_vectorstore

THRESHOLD = 0.4


class AgentState(TypedDict):
    input: str
    result: str

# intent vector setup for routing
# done in rag_agent.py

# routing function (dummy)
def router_node_fn(state: AgentState) -> str:
    return state

router_node = RunnableLambda(router_node_fn)

# sql 
# sql are imported from sql_agent.py

# api
# api are import from api_agent.py

# rag
rag_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant. Use the document to answer the user query."),
    ("human", "{context}\n\nquery: {query}")
])
rag_chain =  rag_prompt | llm
# rag fn
def rag_node_fn(state: AgentState) -> AgentState:
    query = state["input"]
    retrieved_docs = rag_chain_base.retriever.get_relevant_documents(query)
    docs = [doc.page_content for doc in retrieved_docs]
    context = "\n".join(docs) if docs else "No relevant documents found."
    answer = rag_chain.invoke({"context": context, "query": query })
    return {"input": query, "result": answer}

# default llm fn
def default_llm_fn(state: AgentState) -> AgentState:
    response = llm.invoke(state["input"])
    return {"input": state["input"], "result": response}

def keyword_search(state: AgentState) -> str | None:
    query = state["input"].lower()
    # define keyword sets
    sql_keywords = {"table", "column", "schema", "select", "insert", "update", "delete", "row", "database"}
    api_keywords = {"endpoint", "service", "call", "invoke", "post", "get", "put", "delete", "api"}
    rag_keywords = {"specification", "spec", "protocol", "standard", "documentation"}
    # match query to keyword set
    if any(word in query for word in sql_keywords):
        print("[router] keyword match: sql_agent")
        return "sql_agent"
    elif any(word in query for word in api_keywords):
        print("[router] keyword match: api_agent")
        return "api_agent"
    elif any(word in query for word in rag_keywords):
        print("[router] keyword match: rag_chain")
        return "rag_chain"
    return None

# actual router
def semantic_search(state: AgentState) -> str:
    query = state["input"]
    results = intent_vectorstore.similarity_search_with_score(query, k=10)
    if results:
        for doc, score in results:
            print(f"[router] candidate: {doc.metadata['id']} | score: {score:.4f}")
        doc, score = results[0]
        matched_id = doc.metadata.get("id", "default_llm")
        print(f"[router] query: {query} | matched id: {doc.metadata['id']} | score: {score:.4f}")
        if score > THRESHOLD:
            return matched_id
    return "default_llm"

def decide_next_node(state: AgentState) -> str:
    # 1st keyword based search
    ret = keyword_search(state)
    # fallback to semantic
    if not ret:
        # ret = semantic_search(state)
        ret = "default_llm"
    return ret

# build langgraph
graph_builder = StateGraph(AgentState)
# add nodes
graph_builder.add_node("router", router_node)
graph_builder.add_node("sql_agent", sql_subgraph)
graph_builder.add_node("rag_chain", RunnableLambda(rag_node_fn))
graph_builder.add_node("api_agent", api_subgraph)
graph_builder.add_node("default_llm", RunnableLambda(default_llm_fn))

# entry point
graph_builder.set_entry_point("router")
# routing edges
graph_builder.add_conditional_edges("router", decide_next_node, {
    "sql_agent": "sql_agent",
    "rag_chain": "rag_chain",
    "api_agent": "api_agent",
    "default_llm": "default_llm"})
# add edges
graph_builder.add_edge("sql_agent", END)
graph_builder.add_edge("rag_chain", END)
graph_builder.add_edge("api_agent", END)
graph_builder.add_edge("default_llm", END)

# expose runnable
agent: Runnable = graph_builder.compile()
