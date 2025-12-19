from fastapi import Depends
from adapters.agents.lc_agent import SarvantaryamiAgent
from usecase.chat_usecase import ChatUseCase

# Singleton instance of the agent adapter
# In a real app we might load this on startup (lifespan)
_agent_instance = SarvantaryamiAgent()

def get_chat_usecase() -> ChatUseCase:
    return ChatUseCase(_agent_instance)
