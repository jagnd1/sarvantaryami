from typing import TypedDict, Optional
from langchain_core.runnables import Runnable, RunnableLambda
from langchain.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END

# Import actual implementations
# Note: Ideally these sub-agents should also be factories/classes, but we will start by wrapping the main graph.
from adapters.agents.sql_agent import llm, sql_subgraph
from adapters.agents.rag_agent import rag_chain_base
from adapters.agents.api_agent import api_subgraph, intent_vectorstore

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
        retrieved_docs = rag_chain_base.retriever.get_relevant_documents(query)
        docs = [doc.page_content for doc in retrieved_docs]
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
        # 1. Keyword Search
        keyword_match = self._keyword_search(state)
        if keyword_match:
             return keyword_match
        
        # 2. Semantic Search (Optional/Fallback)
        # For now, per original logic, we fallback to default if keywords fail, 
        # but the original code had semantic_search commented out or as a secondary check.
        # Let's re-enable basic semantic search if intended, or stick to default.
        return "default_llm"

    def _keyword_search(self, state: AgentState) -> Optional[str]:
        query = state["input"].lower()
        sql_keywords = {"table", "column", "schema", "select", "insert", "update", "delete", "row", "database"}
        api_keywords = {"endpoint", "service", "call", "invoke", "post", "get", "put", "delete", "api"}
        rag_keywords = {"specification", "spec", "protocol", "standard", "documentation"}

        if any(word in query for word in sql_keywords):
            return "sql_agent"
        elif any(word in query for word in api_keywords):
            return "api_agent"
        elif any(word in query for word in rag_keywords):
            return "rag_chain"
        return None
