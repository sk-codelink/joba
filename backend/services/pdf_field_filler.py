from fastapi import HTTPException

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

from typing import Dict, Any, Optional

class PDFFieldFiller:
    """
    Service for filling PDF form fields using their coordinates
    Uses the field coordinates extracted by FieldExtractionService
    """
    
    def __init__(self):
        pass
    
    def fill_pdf_fields(self, pdf_content: bytes, form_data: Dict[str, Any]) -> bytes:
        """
        Fill PDF form fields using their coordinates
        
        Args:
            pdf_content: Original PDF content in bytes
            form_data: Form data with field values and positions
                      Format: {
                          "formFields": {
                              "field_name": {
                                  "value": "field_value",
                                  "position": {"x": x, "y": y, "width": w, "height": h},
                                  "page": page_number
                              }
                          }
                      }
        
        Returns:
            Filled PDF content as bytes
        """
        doc = None
        if fitz is None:
            raise HTTPException(
                status_code=501,
                detail="PDF filling temporarily disabled (PyMuPDF not installed)."
            )

        try:
            # Open PDF from memory
            doc = fitz.open(stream=pdf_content, filetype="pdf")
            
            form_fields = form_data.get("formFields", {})
            filled_count = 0
            
            for field_name, field_data in form_fields.items():
                value = field_data.get("value", "")
                if not value:
                    continue
                
                # Try to fill the form field directly first
                if self._fill_form_field_directly(doc, field_name, value):
                    filled_count += 1
                    print(f"Filled form field directly: {field_name} = {value}")
                else:
                    # Fallback to text insertion using coordinates
                    if self._fill_field_with_text(doc, field_name, field_data):
                        filled_count += 1
                        print(f"Filled field with text: {field_name} = {value}")
            
            print(f"Successfully filled {filled_count} fields")
            
            # Save the modified PDF to memory
            pdf_bytes = doc.write()
            return pdf_bytes
            
        except Exception as e:
            print(f"Error filling PDF: {str(e)}")
            raise e
        finally:
            if doc is not None:
                doc.close()
    
    def _fill_form_field_directly(self, doc: Any, field_name: str, value: str) -> bool:
        """
        Try to fill form field directly using PyMuPDF's form filling capabilities
        Handles both text fields and checkbox/button fields
        
        Args:
            doc: PyMuPDF document
            field_name: Name of the field to fill
            value: Value to fill
            
        Returns:
            True if successful, False otherwise
        """
        try:
            for page_num in range(len(doc)):
                page = doc[page_num]
                for widget in page.widgets():
                    if widget.field_name == field_name:
                        # Handle different field types
                        field_type = widget.field_type
                        
                        if field_type == 7:  # Text field
                            widget.field_value = str(value)
                        elif field_type in [1, 2]:  # Button/Checkbox field
                            # For checkboxes, set based on boolean value or string representation
                            if isinstance(value, bool):
                                widget.field_value = "Yes" if value else "Off"
                            elif str(value).lower() in ['true', '1', 'yes', 'on']:
                                widget.field_value = "Yes"
                            else:
                                widget.field_value = "Off"
                        else:
                            # Default: try to set as string
                            widget.field_value = str(value)
                        
                        widget.update()
                        return True
            return False
        except Exception as e:
            print(f"Error filling field directly {field_name}: {str(e)}")
            return False
    
    def _fill_field_with_text(self, doc: Any, field_name: str, field_data: Dict[str, Any]) -> bool:
        """
        Fill field by inserting text at the specified coordinates
        
        Args:
            doc: PyMuPDF document
            field_name: Name of the field
            field_data: Field data including value and position
            
        Returns:
            True if successful, False otherwise
        """
        try:
            value = field_data.get("value", "")
            position = field_data.get("position", {})
            page_num = field_data.get("page", 1) - 1  # Convert to 0-based
            
            if not value or not position:
                return False
            
            if page_num >= len(doc) or page_num < 0:
                return False
            
            page = doc[page_num]
            
            # Get position coordinates
            x = position.get("x", 0)
            y = position.get("y", 0)
            font_size = field_data.get("fontSize", 12)
            
            # Convert coordinates (PDF coordinate system has origin at bottom-left)
            page_rect = page.rect
            y_converted = page_rect.height - y
            
            # Insert text
            point = fitz.Point(x, y_converted)
            page.insert_text(
                point,
                value,
                fontsize=font_size,
                color=(0, 0, 0)  # Black color
            )
            
            return True
            
        except Exception as e:
            print(f"Error filling field with text {field_name}: {str(e)}")
            return False
    
    def get_field_at_coordinates(self, pdf_content: bytes, page_num: int, x: float, y: float) -> Optional[str]:
        """
        Find the field name at specific coordinates (for debugging)
        
        Args:
            pdf_content: PDF content in bytes
            page_num: Page number (1-based)
            x, y: Coordinates
            
        Returns:
            Field name if found, None otherwise
        """
        doc = None
        if fitz is None:
            raise HTTPException(
                status_code=501,
                detail="PDF field lookup temporarily disabled (PyMuPDF not installed)."
            )

        try:
            doc = fitz.open(stream=pdf_content, filetype="pdf")
            
            if page_num <= 0 or page_num > len(doc):
                return None
            
            page = doc[page_num - 1]  # Convert to 0-based
            point = fitz.Point(x, y)
            
            for widget in page.widgets():
                if widget.rect.contains(point):
                    return widget.field_name
            
            return None
            
        except Exception as e:
            print(f"Error finding field at coordinates: {str(e)}")
            return None
        finally:
            if doc is not None:
                doc.close()
