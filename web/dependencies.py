from fastapi import Depends
from adapters.agents.lc_agent import SarvantaryamiAgent
from usecase.agent_usecase import AgentUseCase

# Singleton instance of the agent adapter
# In a real app we might load this on startup (lifespan)
_agent_instance = SarvantaryamiAgent()

def get_agent_usecase() -> AgentUseCase:
    return AgentUseCase(_agent_instance)
