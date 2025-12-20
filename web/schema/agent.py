from pydantic import BaseModel, Field

class QueryInput(BaseModel):
    query: str

class QueryResponse(BaseModel):
    status: str = Field(default="success", description="Status of the request")
    response: str = Field(..., description="The response from the agent")
