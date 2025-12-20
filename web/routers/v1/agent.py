from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File, Depends
from web.schema.agent import QueryInput, QueryResponse
from usecase.agent_usecase import AgentUseCase
from web.dependencies import get_agent_usecase

router = APIRouter()

@router.post("/ask", response_model=QueryResponse)
async def ask(
    input: QueryInput, 
    usecase: AgentUseCase = Depends(get_agent_usecase)
):
    try:
        res = await usecase.ask(input.query)
        return QueryResponse(status="success", response=res)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/upload_doc")
async def upload_doc(
    file: UploadFile = File(...), 
    bg_tasks: BackgroundTasks = None,
    usecase: AgentUseCase = Depends(get_agent_usecase)
):
    try:
        file_bytes = await file.read()
        # Ensure usecase method is async or run in threadpool if blocking
        bg_tasks.add_task(usecase.upload_doc, file.filename, file_bytes)
        return {"detail": f"upload started {file.filename}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"error uploading: {str(e)}")

@router.get("/health")
def health_check():
    return {"status": "ok"}
