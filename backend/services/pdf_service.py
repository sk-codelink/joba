import pdfplumber
import io
from typing import Dict, Any, List, Tuple
import PyPDF2
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

class PDFProcessor:
    """PDF processing service for extraction and filling"""
    
    def extract_text(self, pdf_content: bytes) -> str:
        """Extract text from PDF bytes"""
        try:
            text = ""
            with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
            return text.strip()
        except Exception as e:
            raise Exception(f"Error extracting text from PDF: {str(e)}")
    
    def fill_pdf(self, pdf_content: bytes, form_fields: Dict[str, Dict]) -> bytes:
        """
        Fill PDF with text fields based on specified positions
        
        Args:
            pdf_content: The original PDF file content
            form_fields: Dictionary of fields with their values and positions
                         Format: {"field_id": {"value": "text", "position": {"x": 100, "y": 200}}}
                                 
        Returns:
            bytes: The filled PDF content
        """
        try:
            # Create an in-memory bytes buffer for the output PDF
            output_buffer = io.BytesIO()
            
            # Use PyPDF2 to read the original PDF
            reader = PyPDF2.PdfReader(io.BytesIO(pdf_content))
            writer = PyPDF2.PdfWriter()
            
            # Check if the PDF has pages
            if len(reader.pages) == 0:
                raise Exception("The PDF document has no pages")
            
            # Get page dimensions from the first page
            first_page = reader.pages[0]
            page_width = float(first_page.mediabox.width)
            page_height = float(first_page.mediabox.height)
            
            # Calculate scaling factor based on a standard viewport size (1000px wide)
            # This helps ensure positions match between frontend and backend
            viewport_width = 1000.0  # Assumed width of the frontend viewport
            scale_factor = page_width / viewport_width
            
            print(f"PDF dimensions: {page_width} x {page_height}, Scale factor: {scale_factor}")
            
            # Extract the form fields data properly
            processed_fields = {}
            
            # Check if we have a nested structure with formFields
            if "formFields" in form_fields:
                field_dict = form_fields["formFields"]
            else:
                # Use the form_fields directly if it's not nested
                field_dict = form_fields
            
            # Process each page
            for i in range(len(reader.pages)):
                page = reader.pages[i]
                
                # Create temporary buffer for the watermark
                watermark_buffer = io.BytesIO()
                
                # Create a canvas with the page size
                c = canvas.Canvas(watermark_buffer, pagesize=(page_width, page_height))
                
                # Add text fields for this page (assuming all fields go on page 1 for now)
                # For multi-page support, add logic to assign fields to specific pages
                if i == 0:  # Only process first page for now
                    for field_id, field_data in field_dict.items():
                        if not field_data or 'value' not in field_data or not field_data['value']:
                            continue
                            
                        value = field_data['value']
                        
                        # Get position (convert from frontend coordinates if needed)
                        pos = field_data.get('position', {})
                        if not pos:
                            # Skip fields without position data
                            continue
                        
                        # Check if this field has a specific page set
                        field_page = pos.get('page', 0)
                        if field_page != i:  # Skip if this field is not for this page
                            continue
                            
                        # Check if positions are from PyMuPDF (form field positions) or frontend
                        if 'width' in pos and 'height' in pos:
                            # These are direct PDF coordinates from PyMuPDF, no scaling needed
                            # But we still need to adjust Y coordinate for PDF coordinate system
                            x = float(pos.get('x', 0))
                            y = page_height - float(pos.get('y', 0))
                            
                            # For better text positioning in form fields, adjust slightly
                            # This moves text a bit to the right and down from the center point
                            x += 5  # Offset slightly to the right
                            y -= 5  # Offset slightly down
                        else:
                            # These are frontend coordinates, need scaling
                            # Apply scaling to coordinates to match PDF dimensions
                            x = float(pos.get('x', 0)) * scale_factor
                            
                            # PDF coordinates start from bottom left, but browser coordinates 
                            # start from top left, so we need to invert the y-coordinate
                            y = page_height - (float(pos.get('y', 0)) * scale_factor)
                        
                        # Get style attributes
                        font_size = float(field_data.get('fontSize', 12)) * scale_factor
                        font_name = "Helvetica"
                        
                        # Handle font weight
                        font_weight = field_data.get('fontWeight', 'normal')
                        if font_weight == 'bold':
                            font_name = "Helvetica-Bold"
                        
                        # Set font
                        try:
                            c.setFont(font_name, font_size)
                        except Exception:
                            # Fallback to standard font if the specified font is not available
                            c.setFont("Helvetica", font_size)
                        
                        # Set color
                        color = field_data.get('color', 'black')
                        if color == 'black':
                            c.setFillColorRGB(0, 0, 0)
                        else:
                            # Parse common color names or use black as default
                            try:
                                if color == 'red':
                                    c.setFillColorRGB(1, 0, 0)
                                elif color == 'blue':
                                    c.setFillColorRGB(0, 0, 1)
                                elif color == 'green':
                                    c.setFillColorRGB(0, 0.5, 0)
                                # More colors can be added here
                            except Exception:
                                c.setFillColorRGB(0, 0, 0)  # Default to black
                        
                        # Draw text
                        c.drawString(x, y, value)
                        print(f"Added text '{value}' at position ({x}, {y}) with font size {font_size}")
                
                # Save the canvas to the watermark buffer
                c.save()
                
                # Move to the beginning of the buffer
                watermark_buffer.seek(0)
                
                # Create a PDF reader for the watermark
                watermark = PyPDF2.PdfReader(watermark_buffer)
                
                if len(watermark.pages) > 0:
                    # Merge the watermark with the page
                    page.merge_page(watermark.pages[0])
                
                # Add the page to the writer
                writer.add_page(page)
            
            # Write the merged PDF to the output buffer
            writer.write(output_buffer)
            output_buffer.seek(0)
            
            # Return the filled PDF content
            return output_buffer.getvalue()
            
        except Exception as e:
            raise Exception(f"Error filling PDF: {str(e)}")
