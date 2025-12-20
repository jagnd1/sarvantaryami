from typing import TypedDict, Optional
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END

# Import actual implementations
# Note: Ideally these sub-agents should also be factories/classes, but we will start by wrapping the main graph.
from adapters.agents.sql_agent import llm, sql_subgraph
from adapters.agents.rag_agent import rag_chain_base
from adapters.agents.api_agent import api_subgraph, intent_vectorstore

import logging
logger = logging.getLogger(__name__)

class AgentState(TypedDict):
    input: str
    result: str

class SarvantaryamiAgent:
    def __init__(self):
        self.threshold = 0.4
        self.graph = self._build_graph()

    def _build_graph(self) -> Runnable:
        graph_builder = StateGraph(AgentState)

        # Define nodes
        graph_builder.add_node("router", RunnableLambda(self._router_node_fn))
        graph_builder.add_node("sql_agent", sql_subgraph)
        graph_builder.add_node("rag_chain", RunnableLambda(self._rag_node_fn))
        graph_builder.add_node("api_agent", api_subgraph)
        graph_builder.add_node("default_llm", RunnableLambda(self._default_llm_fn))

        # Entry point
        graph_builder.set_entry_point("router")

        # Routing edges
        graph_builder.add_conditional_edges("router", self._decide_next_node, {
            "sql_agent": "sql_agent",
            "rag_chain": "rag_chain",
            "api_agent": "api_agent",
            "default_llm": "default_llm"
        })

        # Final edges
        graph_builder.add_edge("sql_agent", END)
        graph_builder.add_edge("rag_chain", END)
        graph_builder.add_edge("api_agent", END)
        graph_builder.add_edge("default_llm", END)

        return graph_builder.compile()

    def invoke(self, input_text: str) -> str:
        res = self.graph.invoke({"input": input_text})
        # The result from subgraphs might be complex, we aim to extract just the 'result' or 'output' string
        if isinstance(res, dict) and "result" in res:
            return res["result"]
        # Some subgraphs might return different structures (e.g. sql_agent might return a dict with 'output')
        # We might need normalization here, but for now let's assume 'result' or 'output'
        if isinstance(res, dict) and "output" in res: # LangChain AgentExecutor returns 'output'
             return res["output"]
        return str(res)

    # --- Internal Node Functions ---

    def _router_node_fn(self, state: AgentState) -> AgentState:
        # Pass-through node
        return state

    def _rag_node_fn(self, state: AgentState) -> AgentState:
        query = state["input"]
        logger.info(f"[Router] Routing to RAG for: {query}")
        retrieved_docs = rag_chain_base.retriever.get_relevant_documents(query)
        docs = [doc.page_content for doc in retrieved_docs]
        logger.info(f"[RAG] Retrieved {len(docs)} documents")
        context = "\n".join(docs) if docs else "No relevant documents found."
        
        rag_prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a helpful assistant. Use the document to answer the user query."),
            ("human", "{context}\n\nquery: {query}")
        ])
        rag_chain = rag_prompt | llm
        
        answer = rag_chain.invoke({"context": context, "query": query})
        # If answer is an AIMessage, get .content, else str(answer)
        if hasattr(answer, 'content'):
            answer = answer.content
        return {"input": query, "result": str(answer)}

    def _default_llm_fn(self, state: AgentState) -> AgentState:
        response = llm.invoke(state["input"])
        if hasattr(response, 'content'):
             response = response.content
        return {"input": state["input"], "result": str(response)}

    def _decide_next_node(self, state: AgentState) -> str:
        # 1. Semantic Search (primary)
        semantic_match = self._semantic_search(state)
        if semantic_match:
            logger.info(f"[Router] Semantic Match Found: {semantic_match}")
            return semantic_match
            
        # 2. Keyword Search (fallback for specific syntax)
        keyword_match = self._keyword_search(state)
        if keyword_match:
             logger.info(f"[Router] Keyword Match Found: {keyword_match}")
             return keyword_match
        
        logger.info("--- [Router] Falling back to Default LLM ---")
        return "default_llm"

    def _semantic_search(self, state: AgentState) -> Optional[str]:
        query = state["input"]
        # Use relevance threshold (lower distance is better for Cosine Distance)
        results_with_score = intent_vectorstore.similarity_search_with_score(query, k=1)
        if not results_with_score:
            return None
        
        doc, score = results_with_score[0]
        match_id = doc.metadata.get('id')
        logger.info(f"[Router] Semantic check: result='{match_id}', score={score:.4f}, query='{query}'")

        if score < 0.8: 
             return match_id
        return None

    def _keyword_search(self, state: AgentState) -> Optional[str]:
        query = state["input"].lower()
        sql_keywords = {"sql", "select *", "from table", "database schema"}
        api_keywords = {"api endpoint", "invoke service", "post request", "http get"}
        rag_keywords = {"documentation", "spec summary", "protocol definition"}

        if any(word in query for word in sql_keywords):
            return "sql_agent"
        elif any(word in query for word in api_keywords):
            return "api_agent"
        elif any(word in query for word in rag_keywords):
            return "rag_chain"
        return None
