# services/sql_agent.py

from typing import Optional, TypedDict
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langgraph.graph import StateGraph, END
from langchain_community.utilities.sql_database import SQLDatabase
from langchain_community.tools.sql_database.tool import QuerySQLDatabaseTool
from langchain_ollama import ChatOllama


from infrastructure.config import settings

# llm
llm = ChatOllama(model=settings.LLM_MODEL, base_url=settings.OLLAMA_BASE_URL)

# sql agent
db_uri = settings.DB_URI
db = SQLDatabase.from_uri(db_uri)
sql_tool = QuerySQLDatabaseTool(db=db)


table_selector_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are an AI SQL assistant. Your task is to select the most relevant table name from the provided list."),
    ("human", "User query: {input}\nAvailable tables: {tables}\n\nRespond with only the table name, no explanation, no quotes.")
])

sql_gen_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are an expert SQL generator. Given a user query and table schema, return the correct SQL query to execute."),
    ("human", "User query: {input}\n\nTable schema:\n{schema}\n\nRespond only with the SQL query (no explanations, no markdown).")
])
sql_gen_chain = sql_gen_prompt | llm | StrOutputParser()

table_selector_chain = table_selector_prompt | llm | StrOutputParser()
class SqlAgentState(TypedDict):
    input: str
    table_list: Optional[list[str]]
    selected_table: Optional[str]
    query: Optional[str]
    result: Optional[str]

import logging

logger = logging.getLogger(__name__)

# list all the tables
def list_tables_node_fn(state: SqlAgentState) -> SqlAgentState:
    tables = db.get_usable_table_names()
    return {**state, "table_list": tables}

# select relevant table
def select_table_node_fn(state: SqlAgentState) -> SqlAgentState:
    if not state["table_list"]:
        raise ValueError("no tables available to select from")
    table_list_str = ", ".join(state["table_list"])
    selected = table_selector_chain.invoke({"tables": table_list_str, "input": state["input"]})
    selected = selected.strip()
    if selected not in state["table_list"]:
        raise ValueError(f"selected table '{selected}' is not in the available list: {state['table_list']}")
    logger.info(f"selected table: {selected}")
    return {**state, "selected_table": selected}

def generate_execute_sql_node_fn(state: SqlAgentState) -> SqlAgentState:
    if not state["selected_table"]:
        raise ValueError("no table selected for SQL generation")
    logger.info(f"selected table: {state['selected_table']}")
    schema = db.get_table_info([state["selected_table"]])
    sql_query = sql_gen_chain.invoke({
        "input": state["input"],
        "table": state["selected_table"],
        "schema": schema
    })
    sql_query = sql_query.strip()
    if not sql_query:
        raise ValueError("generated sql query is empty")
    logger.info(f"generated sql query: {sql_query}")
    
    from tenacity import retry, stop_after_attempt, wait_fixed
    
    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    def execute_sql_safe(query):
        return sql_tool.run(query)

    try:
        result = execute_sql_safe(sql_query)
    except Exception as e:
        logger.error(f"error executing sql query: {e}")
        raise ValueError(f"error executing sql query: {e}")
    logger.info(f"sql query: {sql_query}, result: {result}")
    return {"input": state["input"], "selected_table": state["selected_table"], "query": sql_query, 
            "result": result}

sql_subgraph_builder = StateGraph(SqlAgentState)
# add nodes
sql_subgraph_builder.add_node("list_tables", list_tables_node_fn) 
sql_subgraph_builder.add_node("select_table", select_table_node_fn)
sql_subgraph_builder.add_node("generate_and_execute", generate_execute_sql_node_fn)
# edges
sql_subgraph_builder.set_entry_point("list_tables")
sql_subgraph_builder.add_edge("list_tables", "select_table")
sql_subgraph_builder.add_edge("select_table", "generate_and_execute")
sql_subgraph_builder.add_edge("generate_and_execute", END)
# compile
sql_subgraph = sql_subgraph_builder.compile()