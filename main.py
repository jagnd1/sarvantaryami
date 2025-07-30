from fastapi import FastAPI
from api.chatbot import router as chatbot_router

app = FastAPI(title="FM assistant!")
app.include_router(chatbot_router, prefix="/cb", tags=["cb"])

