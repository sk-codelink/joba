import os
import json
import logging
import asyncio
from typing import Dict, Any, Optional
from fastapi import HTTPException

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

logger = logging.getLogger(__name__)

class GeminiService:
    
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.model = None
        
        if not self.api_key:
            logger.warning("No GEMINI_API_KEY found. Gemini service will not be available.")
        elif not GEMINI_AVAILABLE:
            logger.warning("Google Generative AI package not installed. Gemini service will not be available.")
        else:
            try:
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel('gemini-2.5-flash')
                logger.info("Gemini 2.5 flash initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini API: {e}")
                self.model = None
    
    async def generate_content(self, prompt: str) -> str:
        if not self.model or not GEMINI_AVAILABLE:
            raise HTTPException(
                status_code=503, 
                detail="Gemini AI service is not available. Please check API key configuration."
            )
        
        try:
            return await self._use_gemini_api(prompt)
        except Exception as e:
            logger.error(f"Gemini AI service error: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"AI form filling failed: {str(e)}"
            )
    
    async def _use_gemini_api(self, prompt: str) -> str:
        try:
            enhanced_prompt = f"""
You are an expert AI assistant specialized in intelligently filling medical/insurance forms based on user input.

INSTRUCTIONS:
1. Analyze the user input carefully to extract relevant information
2. Match the extracted information to the most appropriate form fields using BOTH the technical field name AND the human-readable label
3. Use intelligent reasoning to determine the best field matches
4. Return ONLY a valid JSON object with field names as keys and extracted values as values
5. Include a "reasoning" field explaining your matching logic
6. For checkbox fields, use true/false boolean values
7. For text fields, provide the most appropriate extracted text
8. If you cannot determine a value with confidence, do not include that field in the response

CRITICAL RULES:
- ONLY return valid JSON, no additional text or explanations outside the JSON
- Field names must match exactly as provided in the form fields list
- Use both technical field names and human labels to make intelligent matches
- Prioritize accuracy over completeness - only fill fields you're confident about

{prompt}

Remember: Return ONLY the JSON response, no additional text.
"""

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: self.model.generate_content(enhanced_prompt)
            )
            
            response_text = response.text.strip()
            
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            
            try:
                json.loads(response_text)
                logger.info("Gemini API response received and validated")
                return response_text
            except json.JSONDecodeError:
                logger.error("Invalid JSON response from Gemini API")
                raise Exception("Gemini API returned invalid JSON response")
                
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            raise
