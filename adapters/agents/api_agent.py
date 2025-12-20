import json
import logging
from typing import List, Optional, TypedDict, Dict, Any, Annotated
import requests
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
from langchain_community.vectorstores.utils import DistanceStrategy
from langchain_core.tools import tool
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from langchain_core.runnables import Runnable, RunnableLambda
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from adapters.agents.sql_agent import llm
from adapters.agents.rag_agent import intent_docs, embeddings

logger = logging.getLogger(__name__)

# --- 1. OpenAPI Spec Loading & Parsing ---

class OpenApiManager:
    def __init__(self, spec_path: str):
        self.spec_path = spec_path
        self.spec = self._load_spec()
        # Fallback to localhost if server url not found
        self.server_url = self.spec.get("servers", [{"url": "http://localhost:8000"}])[0]["url"]
        self.paths = self.spec.get("paths", {})
        self.operation_map = self._build_operation_map()

    def _load_spec(self) -> Dict:
        try:
            with open(self.spec_path, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"OpenAPI spec not found at {self.spec_path}")
            return {}

    def _build_operation_map(self) -> Dict[str, Dict]:
        """Map operationId to method, path, and details"""
        ops = {}
        for path, methods in self.paths.items():
            for method, details in methods.items():
                if method.lower() not in ["get", "post", "put", "delete", "patch", "options", "head"]:
                    continue
                op_id = details.get("operationId")
                if op_id:
                    ops[op_id] = {
                        "method": method.upper(),
                        "path": path,
                        "details": details
                    }
        return ops

    def get_operation_details(self, operation_id: str) -> Optional[Dict]:
        return self.operation_map.get(operation_id)
    
    def get_relevant_schema_str(self, operation_ids: List[str]) -> str:
        """Extracts only the relevant parts of the spec for the LLM context"""
        relevant_specs = []
        for op_id in operation_ids:
            op = self.operation_map.get(op_id)
            if op:
                relevant_specs.append({
                    "operationId": op_id,
                    "path": op["path"],
                    "method": op["method"],
                    "summary": op["details"].get("summary"),
                    "parameters": op["details"].get("parameters", []),
                    "requestBody": op["details"].get("requestBody", {})
                })
        return json.dumps(relevant_specs, indent=2)

# Initialize Manager
openapi_manager = OpenApiManager("infrastructure/openapi.json")

# --- 2. Intent Generation ---

def generate_api_agent_intents_from_openapi(api_spec_dict: dict):
    global intent_docs
    
    # We rely on openapi_manager being populated
    if not openapi_manager.operation_map:
        return []

    for op_id, info in openapi_manager.operation_map.items():
        summary = info["details"].get("summary", "No description")
        path = info["path"]
        method = info["method"]
        service_hint = path.strip("/").split("/")[1] if len(path.strip("/").split("/")) > 1 else "api"
        
        doc_text = (
            f"Invoke the {method} {path} endpoint of {service_hint} service "
            f"to {summary.lower()}. "
            f"OperationID: {op_id}"
        )
        # Check if already exists to prevent dupes (naive check)
        if not any(d.metadata.get("operation_id") == op_id for d in intent_docs):
            doc = Document(page_content=doc_text, metadata={"id": "api_agent", "operation_id": op_id})
            intent_docs.append(doc)
    return intent_docs

# Populate intents and build vectorstore
generate_api_agent_intents_from_openapi(openapi_manager.spec)
intent_vectorstore = FAISS.from_documents(intent_docs, embeddings, distance_strategy=DistanceStrategy.COSINE)


# --- 3. Tool Definition ---

from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

@tool
@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(requests.RequestException))
def call_api_endpoint(operation_id: str, path_params: Dict[str, Any] = {}, query_params: Dict[str, Any] = {}, body: Dict[str, Any] = {}) -> str:
    """
    Executes an API call for a specific operationId.
    
    Args:
        operation_id: The OpenAPI operationId to call.
        path_params: Dictionary of path parameters (e.g., {"id": "123"}).
        query_params: Dictionary of query parameters.
        body: Dictionary representing the JSON body.
    """
    op = openapi_manager.get_operation_details(operation_id)
    if not op:
        return f"Error: Operation '{operation_id}' not found."

    method = op["method"]
    path_template = op["path"]
    
    # Resolve Path Params
    try:
        url_path = path_template.format(**path_params)
    except KeyError as e:
        return f"Error: Missing path parameter {e}. Please provide all path parameters required by the schema."
    except Exception as e:
        return f"Error formatting path: {str(e)}"
    
    url = f"{openapi_manager.server_url}{url_path}"
    
    logger.info(f"Invoking API: {method} {url} | Params: {query_params} | Body: {body}")

    
    try:
        if method == "GET":
            resp = requests.get(url, params=query_params)
        elif method == "POST":
            resp = requests.post(url, params=query_params, json=body)
        elif method == "PUT":
            resp = requests.put(url, params=query_params, json=body)
        elif method == "DELETE":
            resp = requests.delete(url, params=query_params)
        else:
            return f"Error: Unsupported method {method}"
            
        return f"Status: {resp.status_code}\nResponse: {resp.text}"
    except Exception as e:
        return f"Error executing request: {str(e)}"


# --- 4. Agent Logic (ReAct Loop) ---

class ApiAgentState(TypedDict):
    input: str
    relevant_ops: List[str]
    messages: Annotated[List[BaseMessage], add_messages]
    result: Optional[str]

def retrieve_ops_node(state: ApiAgentState) -> ApiAgentState:
    """Find relevant operations based on the input query"""
    query = state["input"]
    results = intent_vectorstore.similarity_search(query, k=2)
    ops = [doc.metadata["operation_id"] for doc in results if doc.metadata.get("operation_id")]
    logger.info(f"[ApiAgent] Found relevant ops: {ops}")
    
    # Initialize messages with user input if empty
    msgs = state.get("messages", [])
    if not msgs:
        msgs = [HumanMessage(content=query)]
    
    return {"relevant_ops": ops, "messages": msgs}

def model_node(state: ApiAgentState) -> ApiAgentState:
    """Decide next action using LLM with tools binding"""
    ops = state["relevant_ops"]
    messages = state["messages"]
    
    if not ops:
        sys_content = "you are an api assistant. unfortunately, no relevant api operations were found. please inform the user."
    else:
        schema_context = openapi_manager.get_relevant_schema_str(ops)
        sys_content = f"""you are an expert api assistant.
available api schemas:
{schema_context}

task: satisfy the user request by calling 'call_api_endpoint'.
rules:
1. extract parameters carefully. check if a parameter is in 'path', 'query', or 'body'.
2. mandatory path parameters must go in 'path_params'.
3. query parameters must go in 'query_params'.
4. post/put data must go in 'body'.
5. do not guess ids. if an id is missing, ask the user.
6. summarize the api response for the user.
7. example tool call: call_api_endpoint(operation_id="get_currency...", path_params={{"id": "usd"}}, query_params={{}}, body={{}})
"""
    
    # Prepend system message to the current interaction context
    # We create a new list for the prompt to avoid appending SystemMessage to the state history repeatedly loop after loop
    prompt_messages = [SystemMessage(content=sys_content)] + messages
    
    llm_with_tools = llm.bind_tools([call_api_endpoint])
    response = llm_with_tools.invoke(prompt_messages)
    
    return {"messages": [response]}

def finalize_node(state: ApiAgentState) -> ApiAgentState:
    """Extract final answer to 'result' key for compatibility"""
    last_msg = state["messages"][-1]
    content = last_msg.content if isinstance(last_msg, BaseMessage) else str(last_msg)
    return {"result": content}

# --- Graph Construction ---

graph_builder = StateGraph(ApiAgentState)

graph_builder.add_node("retrieve", retrieve_ops_node)
graph_builder.add_node("agent", model_node)
graph_builder.add_node("tools", ToolNode([call_api_endpoint]))
graph_builder.add_node("finalize", finalize_node)

graph_builder.set_entry_point("retrieve")

graph_builder.add_edge("retrieve", "agent")

graph_builder.add_conditional_edges(
    "agent",
    tools_condition,
    {
        "tools": "tools",
        END: "finalize"
    }
)

graph_builder.add_edge("tools", "agent")
graph_builder.add_edge("finalize", END)

api_subgraph = graph_builder.compile()
