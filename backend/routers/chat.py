from fastapi import APIRouter, HTTPException
from google import genai
from dotenv import load_dotenv
from pydantic import BaseModel 
import os
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
router = APIRouter()
class ChatRequest(BaseModel):
    user_message : str

@router.post("/")
async def chat(request : ChatRequest):
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=request.user_message,
            )
        return response.text

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat failed:{str(e)}")