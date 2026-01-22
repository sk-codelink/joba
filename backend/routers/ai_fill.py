from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import logging
import json
from difflib import SequenceMatcher

from services.gemini_service import GeminiService

router = APIRouter()
logger = logging.getLogger(__name__)

class AIFillRequest(BaseModel):
    user_input: str
    form_fields: Dict[str, Any]

class AIFillResponse(BaseModel):
    filled_fields: Dict[str, Any]
    reasoning: str


def get_best_match(user_value: str, options: List[str], threshold: float = 0.4) -> Optional[str]:
    """
    Find the best matching option value using fuzzy string matching.
    
    Args:
        user_value: The value provided by user (possibly misspelled)
        options: List of valid option values
        threshold: Minimum similarity ratio to consider a match (0.0 to 1.0)
    
    Returns:
        The best matching option value, or None if no good match found
    """
    if not user_value or not options:
        return None
    
    user_value_lower = user_value.lower().strip()
    
    # First, check for exact match (case-insensitive)
    for option in options:
        if option.lower().strip() == user_value_lower:
            return option
    
    # Find the best fuzzy match
    best_match = None
    best_ratio = 0.0
    
    for option in options:
        option_lower = option.lower().strip()
        
        # Calculate similarity ratio
        ratio = SequenceMatcher(None, user_value_lower, option_lower).ratio()
        
        # Also check if user_value is a substring or prefix
        if user_value_lower in option_lower or option_lower.startswith(user_value_lower):
            ratio = max(ratio, 0.7)  # Boost score for substring/prefix matches
        
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = option
    
    # Return the match only if it meets the threshold
    if best_ratio >= threshold:
        logger.info(f"Fuzzy matched '{user_value}' -> '{best_match}' (ratio: {best_ratio:.2f})")
        return best_match
    
    return None


def build_field_options_map(form_fields: Dict[str, Any]) -> Dict[str, List[str]]:
    """
    Build a map of field names to their available option values.
    
    Args:
        form_fields: The form fields dictionary
    
    Returns:
        Dict mapping field_name to list of valid option values
    """
    options_map = {}
    
    for field_name, field_data in form_fields.items():
        field_type = field_data.get("fieldType", "")
        options = field_data.get("options", [])
        
        # Fields that have predefined options
        if field_type in ["radio", "dropdown", "listbox", "select"] and options:
            option_values = []
            for opt in options:
                if isinstance(opt, dict):
                    # Options can be {'value': 'Male', 'label': 'Male', ...}
                    value = opt.get("value", opt.get("label", ""))
                    if value:
                        option_values.append(str(value))
                elif isinstance(opt, str):
                    option_values.append(opt)
            
            if option_values:
                options_map[field_name] = option_values
    
    return options_map


def post_process_filled_fields(
    filled_fields: Dict[str, Any], 
    options_map: Dict[str, List[str]]
) -> Dict[str, Any]:
    """
    Post-process AI-filled fields to ensure option values match available options.
    
    Args:
        filled_fields: The fields filled by AI
        options_map: Map of field names to valid option values
    
    Returns:
        Processed fields with corrected option values
    """
    processed = {}
    
    for field_name, value in filled_fields.items():
        if field_name in options_map and value:
            # This field has predefined options - find best match
            options = options_map[field_name]
            matched_value = get_best_match(str(value), options)
            
            if matched_value:
                processed[field_name] = matched_value
                if matched_value != value:
                    logger.info(f"Field '{field_name}': corrected '{value}' -> '{matched_value}'")
            else:
                # No good match found - skip this field or keep original
                logger.warning(f"Field '{field_name}': no match found for '{value}' in options {options}")
                # Optionally, we can still set the closest match even below threshold
                # For now, we skip fields with no good match
        else:
            # Regular field - keep as is
            processed[field_name] = value
    
    return processed


@router.post("/ai-fill", response_model=AIFillResponse)
async def ai_fill_form(request: AIFillRequest):
    try:
        gemini_service = GeminiService()
        
        # Build options map for fields with predefined values
        options_map = build_field_options_map(request.form_fields)
        
        field_descriptions = []
        for field_name, field_data in request.form_fields.items():
            field_type = field_data.get("fieldType", "text")
            input_type = field_data.get("inputType", "text")
            field_label = field_data.get("label", field_name)
            
            # Determine display type
            if input_type == "checkbox" or field_type == "checkbox":
                display_type = "checkbox"
            elif field_type in ["radio", "dropdown", "listbox", "select"]:
                display_type = field_type
            else:
                display_type = "text"
            
            # Build description with options if available
            combined_description = f"{field_name} | {field_label} ({display_type})"
            
            # Add options for fields that have them
            if field_name in options_map:
                options_str = ", ".join(f'"{opt}"' for opt in options_map[field_name])
                combined_description += f" [OPTIONS: {options_str}]"
            
            field_descriptions.append(f"- {combined_description}")
        
        prompt = f"""
You are an intelligent form filling assistant. Based on the user's input, fill the appropriate form fields with relevant information.

User Input:
{request.user_input}

Available Form Fields:
{chr(10).join(field_descriptions)}

Instructions:
1. Use ONLY the field_name (before the |) as the key in your response
2. For text fields: Extract relevant information from the user input and fill with appropriate text
3. For checkbox fields: Set to true if the condition is met, false otherwise
4. For radio/dropdown/listbox fields with [OPTIONS]: You MUST select one of the listed option values. Match the user's input to the CLOSEST matching option, even if the user misspells or uses different wording. For example:
   - If user says "mle" or "male" or "man" and options are ["Male", "Female"], select "Male"
   - If user says "fmale" or "woman" and options are ["Male", "Female"], select "Female"
   - Always return the EXACT option value from the OPTIONS list, not what the user typed
5. Match based on BOTH the technical field_name AND the human_readable_label
6. Only fill fields where you have relevant information - leave others empty
7. Be accurate and conservative - don't guess if you're not confident for text fields, but DO make your best match for fields with OPTIONS

Response format:
{{
    "field_name_1": "extracted value or exact option value",
    "field_name_2": true/false for checkboxes,
    "reasoning": "Brief explanation of your mapping decisions"
}}

Respond with valid JSON only.
"""
        
        ai_response = await gemini_service.generate_content(prompt)
        
        try:
            parsed_response = json.loads(ai_response)
            filled_fields = {k: v for k, v in parsed_response.items() if k != "reasoning"}
            reasoning = parsed_response.get("reasoning", "AI processed the input and mapped relevant information to form fields.")
            
            # Post-process to ensure option values match available options (fuzzy matching safety net)
            filled_fields = post_process_filled_fields(filled_fields, options_map)
            
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
