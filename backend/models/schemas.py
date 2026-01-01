from pydantic import BaseModel
from typing import Dict, Any, Optional, List

class PDFUploadResponse(BaseModel):
    """Response for PDF upload and extraction"""
    filename: str
    extracted_fields: Dict[str, Any]

class PDFFillResponse(BaseModel):
    """Response for PDF fill form data"""
    success: bool
    message: str
    form_data: Dict[str, Any]

class ErrorResponse(BaseModel):
    """Error response model"""
    error: str
    detail: str
