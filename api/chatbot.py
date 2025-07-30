# api/chatbot.py

from fastapi import APIRouter, BackgroundTasks, HTTPException,  UploadFile, File
from pydantic import BaseModel
from services.lc_agent import agent
from services.upload import _upload_doc


router = APIRouter()

class QueryInput(BaseModel):
    query: str

@router.post("/ask")
async def ask(input: QueryInput):
    try:
        res = agent.invoke({"input": input.query})
        return {"response": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload_doc")
async def upload_doc(file: UploadFile = File(...), bg_tasks: BackgroundTasks = None):
    try:
        file_bytes = await file.read()
        bg_tasks.add_task(_upload_doc, file.filename, file_bytes)
        return {"detail": f"upload started {file.filename}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"error uploading: str{e}")



@router.get("/health")
def health_check():
    return {"status": "ok"}
