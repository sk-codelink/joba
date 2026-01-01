from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
import logging

from services.gemini_service import GeminiService

router = APIRouter()
logger = logging.getLogger(__name__)

class AIFillRequest(BaseModel):
    user_input: str
    form_fields: Dict[str, Any]

class AIFillResponse(BaseModel):
    filled_fields: Dict[str, Any]
    reasoning: str

@router.post("/ai-fill", response_model=AIFillResponse)
async def ai_fill_form(request: AIFillRequest):
    try:
        gemini_service = GeminiService()
        
        field_descriptions = []
        for field_name, field_data in request.form_fields.items():
            field_type = "checkbox" if field_data.get("inputType") == "checkbox" else "text"
            field_label = field_data.get("label", field_name)
            
            combined_description = f"{field_name} | {field_label}"
            field_descriptions.append(f"- {combined_description} ({field_type})")
        
        prompt = f"""
You are an intelligent form filling assistant. Based on the user's input, fill the appropriate form fields with relevant information.

User Input:
{request.user_input}

Available Form Fields (format: field_name | human_readable_label):
{chr(10).join(field_descriptions)}

Instructions:
1. Use ONLY the field_name (before the |) as the key in your response
2. For text fields: Extract relevant information from the user input and fill the field with appropriate text
3. For checkbox fields: Set to true if the condition is met, false otherwise
4. Match based on BOTH the technical field_name AND the human_readable_label
5. Only fill fields where you have relevant information - leave others empty
6. Be accurate and conservative - don't guess if you're not confident
7. Return the result as a JSON object with field names as keys and their values

Response format:
{{
    "field_name_1": "extracted value" or true/false for checkboxes,
    "field_name_2": "another value",
    "reasoning": "Brief explanation of your mapping decisions"
}}

Respond with valid JSON only.
"""
        
        ai_response = await gemini_service.generate_content(prompt)
        
        import json
        try:
            parsed_response = json.loads(ai_response)
            filled_fields = {k: v for k, v in parsed_response.items() if k != "reasoning"}
            reasoning = parsed_response.get("reasoning", "AI processed the input and mapped relevant information to form fields.")
        except json.JSONDecodeError:
            logger.warning("AI response was not valid JSON, using fallback")
            filled_fields = {}
            reasoning = "Unable to parse AI response properly."
        
        return AIFillResponse(
            filled_fields=filled_fields,
            reasoning=reasoning
        )
        
    except Exception as e:
        logger.error(f"Error in AI form filling: {str(e)}")
        raise HTTPException(status_code=500, detail=f"AI form filling failed: {str(e)}")
