from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from fastapi.responses import StreamingResponse
import json
from services.pdf_field_filler import PDFFieldFiller
import io
router = APIRouter()

pdf_filler = PDFFieldFiller()

@router.post("/get_pdf", response_class=StreamingResponse)
async def get_pdf(
    pdf_file: UploadFile = File(...),
    form_data: str = Form(...)
):
    """
    Get a PDF with the fields filled
    
    Args:
        pdf_file: The original PDF file
        form_data: JSON string with field data
    
    Returns:
        The PDF file with the fields filled
    """
    try:
        # Validate PDF file
        if not pdf_file.filename or not pdf_file.filename.lower().endswith('.pdf'):
            raise HTTPException(
                status_code=400,
                detail="Invalid file format. Please upload a PDF file."
            )
            
        # Get file size
        file_size = 0
        content = await pdf_file.read()
        file_size = len(content)
        
        # Check if file is empty
        if file_size == 0:
            raise HTTPException(
                status_code=400,
                detail="The uploaded PDF file is empty."
            )
            
        # Log file details
        print(f"Processing PDF: {pdf_file.filename}, size: {file_size / 1024:.2f} KB")
        
        # Parse form data
        try:
            form_fields_data = json.loads(form_data)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid JSON in form data: {str(e)}"
            )
        
        # Count fields with values
        field_count = 0
        if "formFields" in form_fields_data:
            for field_id, field_data in form_fields_data["formFields"].items():
                if field_data and field_data.get("value"):
                    field_count += 1
        
        print(f"Processing {field_count} fields with values")
        
        if field_count == 0:
            print("Warning: No fields with values to process")
        
        # Fill the PDF using coordinates
        try:
            filled_pdf = pdf_filler.fill_pdf_fields(content, form_fields_data)
            
            # Verify we got valid PDF data back
            if not filled_pdf or len(filled_pdf) < 100:
                raise ValueError("PDF filling process returned invalid data")
                
            # Return the filled PDF
            return StreamingResponse(
                io.BytesIO(filled_pdf),
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f"attachment; filename=filled_{pdf_file.filename}"
                }
            )
        except Exception as pdf_error:
            print(f"PDF processing error: {str(pdf_error)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error processing PDF: {str(pdf_error)}"
            )
    except HTTPException as he:
        # Re-raise HTTP exceptions
        raise he
    except Exception as e:
        # Handle any other exceptions
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Error filling PDF: {str(e)}"
        )

