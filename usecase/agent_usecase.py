from adapters.agents.lc_agent import SarvantaryamiAgent
from adapters.upload import _upload_doc

class AgentUseCase:
    def __init__(self, agent_service: SarvantaryamiAgent):
        self.agent = agent_service

    async def ask(self, query: str) -> str:
        # Business logic can go here (logging, quota checking, etc.)
        return self.agent.invoke(query)

    async def upload_doc(self, filename: str, file_bytes: bytes):
        # We wrap the existing logic. In a real DB scenario, we might save metadata first.
        _upload_doc(filename, file_bytes)
        return f"Upload started for {filename}"
