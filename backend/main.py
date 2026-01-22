from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from dotenv import load_dotenv

from routers.extract import router as extract_router
from routers.get_pdf import router as get_pdf_router
from routers.ai_fill import router as ai_fill_router
from routers.chat import router as chat
load_dotenv()

app = FastAPI(
    title="JOBA Healthcare PDF Processor",
    description="PDF form field extraction and filling using direct coordinate-based approach",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(extract_router, prefix="/api/v1", tags=["extraction"])
app.include_router(get_pdf_router, prefix="/api/v1", tags=["get_pdf"])
app.include_router(ai_fill_router, prefix="/api/v1", tags=["ai-filling"])
app.include_router(chat,prefix="/api/v1",tags=["chat"])

@app.get("/")
async def root():
    return {"message": "JOBA Healthcare PDF Processor API", "status": "running and healthy"}

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
