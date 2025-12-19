import json
from typing import List, Optional, TypedDict
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END
from langchain_community.utilities.openapi import OpenAPISpec
from langchain_community.agent_toolkits.openapi.toolkit import OpenAPIToolkit
from langchain_community.agent_toolkits.openapi.spec import reduce_openapi_spec
from langchain_community.agent_toolkits.openapi import planner
from langchain_community.tools.json.tool import JsonSpec 
from langchain_core.output_parsers import StrOutputParser
from langchain_community.utilities.requests import RequestsWrapper 
from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
from langchain_community.vectorstores.utils import DistanceStrategy
from langchain.agents import AgentExecutor

from adapters.agents.sql_agent import llm
from adapters.agents.rag_agent import intent_docs, embeddings

def generate_api_agent_intents_from_openapi(api_spec_dict: dict):
    info_sect = api_spec_dict.get("info", {})
    paths = api_spec_dict.get("paths", {})
    for path, methods in paths.items():
        for method, details in methods.items():
            operation_id = details.get("operationId", "UnnamedOperation")
            summary = details.get("summary", "No description")
            service_hint = path.strip("/").split("/")[1] if len(path.strip("/").split("/")) > 1 else "api"
            doc_text = (
                f"Invoke the {method.upper()} {path} endpoint of {service_hint} service "
                f"defined in the OpenAPI spec to {summary.lower()}. "
                f"Use operationId '{operation_id}'."
            )
            # print(f"intent gen: {doc_text}")
            doc = Document(page_content=doc_text, metadata={"id": "api_agent", 
                                                            "operation_id": operation_id})
            intent_docs.append(doc)
    return intent_docs

intent_vectorstore = FAISS.from_documents(intent_docs, embeddings, 
                                          distance_strategy=DistanceStrategy.COSINE)

# load the openapi spec
def init(opeapi_json_file_path: str):
    with open(opeapi_json_file_path, "r") as f:
        api_spec_dict = json.load(f)
    if "servers" not in api_spec_dict:
        api_spec_dict["servers"] = [{"url": "http://localhost:8000"}]
    reduced_api_spec_dict = reduce_openapi_spec(api_spec_dict)
    requests_wrapper = RequestsWrapper()
    return planner.create_openapi_agent(api_spec=reduced_api_spec_dict, 
                                             requests_wrapper=requests_wrapper, llm=llm, 
                                             allow_dangerous_requests=True,
                                             verbose=True)

api_sub_agent:AgentExecutor = init("infrastructure/openapi.json")

# define the agent state
class ApiAgentState(TypedDict):
    input: str
    api_list: Optional[list[str]]
    selected_api: Optional[str]
    result: Optional[str]

def exec_api_node_fn(state: ApiAgentState) -> ApiAgentState:
    try:
        result = api_sub_agent.invoke({"input": state["input"]})
        print(f"result: {result}")
        return {**state, "result": result}
    except Exception as e:
        print(f"error in api_sub_agent invocation: {e}")
        return {**state, "result": f"error during api exec: {e}"}
    
# build the api sub graph
api_subgraph_builder = StateGraph(ApiAgentState)
# add nodes
api_subgraph_builder.add_node("exec_api", exec_api_node_fn)
# edges
api_subgraph_builder.set_entry_point("exec_api")
api_subgraph_builder.add_edge("exec_api", END)
# Compile the graph
api_subgraph = api_subgraph_builder.compile()
