from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import time

from models.schemas import PDFUploadResponse, ErrorResponse
from services.field_extraction_service import FieldExtractionService

router = APIRouter()

# Initialize services
field_extractor = FieldExtractionService()

@router.post("/extract", response_model=PDFUploadResponse)
async def extract_pdf_fields(file: UploadFile = File(...)):
    """
    Upload a PDF and extract form fields with their coordinates directly from the PDF
    """
    # Validate file type
    if not file.content_type == "application/pdf":
        raise HTTPException(
            status_code=400, 
            detail="File must be a PDF"
        )
    
    try:
        start_time = time.time()
        
        # Read PDF content
        pdf_content = await file.read()
        
        # Extract form fields directly from PDF
        extracted_result = field_extractor.extract_form_fields(pdf_content)
        
        if extracted_result.get("error"):
            raise HTTPException(
                status_code=400,
                detail=f"Error extracting fields: {extracted_result['error']}"
            )
        
        if extracted_result.get("total_fields", 0) == 0:
            raise HTTPException(
                status_code=400,
                detail="No form fields found in the PDF. This might not be a fillable form."
            )
        
        # Prepare fields for frontend
        frontend_data = field_extractor.prepare_fields_for_frontend(extracted_result)
        
        processing_time = time.time() - start_time
        print(f"Field extraction completed in {processing_time:.2f} seconds")
        
        return PDFUploadResponse(
            filename=file.filename,
            extracted_fields=frontend_data,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Processing failed: {str(e)}"
        )

@router.get("/test")
async def test_endpoint():
    """Test endpoint to verify the API is working"""
    return {"message": "Extract API is working", "timestamp": time.time()}
