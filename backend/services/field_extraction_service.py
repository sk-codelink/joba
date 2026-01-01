from fastapi import HTTPException

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

import io
from typing import Dict, Any, List, Tuple, Optional

class FieldExtractionService:
    """
    Service for extracting form fields and their coordinates from PDF files
    Replaces Gemini and Mistral services with direct PDF field extraction
    """
    
    def __init__(self):
        pass
    
    def extract_form_fields(self, pdf_content: bytes) -> Dict[str, Any]:
        """
        Extract all form fields and their coordinates from a PDF file
        Uses robust extraction to handle all field types and error conditions
        
        Args:
            pdf_content: PDF file content in bytes
            
        Returns:
            Dictionary with extracted fields and metadata
        """
        doc = None
        if fitz is None:
            raise HTTPException(
                status_code=501,
                detail="PDF field extraction temporarily disabled (PyMuPDF not installed)."
            )

        try:
            # Open PDF from memory stream
            doc = fitz.open(stream=pdf_content, filetype="pdf")
            
            all_fields = {}
            total_count = 0
            total_pages = len(doc)
            
            print(f"Analyzing PDF with {total_pages} pages...")
            
            # Extract fields using widgets method
            for page_number in range(total_pages):
                try:
                    page = doc[page_number]
                    widgets = page.widgets()
                    
                    if widgets:
                        for widget in widgets:
                            try:
                                field_name = widget.field_name
                                
                                if not field_name:
                                    # Generate a unique name for unnamed fields
                                    field_name = f"unnamed_field_{page_number + 1}_{total_count}"
                                
                                # Handle duplicate field names by appending a counter
                                original_name = field_name
                                counter = 1
                                while field_name in all_fields:
                                    field_name = f"{original_name}_{counter}"
                                    counter += 1
                                
                                # Try to get field value safely
                                field_value = ""
                                try:
                                    field_value = widget.field_value if widget.field_value else ""
                                except:
                                    field_value = ""
                                
                                # Try to get field type safely
                                try:
                                    field_type = widget.field_type
                                except:
                                    field_type = -1  # Unknown type
                                
                                # Try to get coordinates safely
                                try:
                                    rect = [widget.rect.x0, widget.rect.y0, widget.rect.x1, widget.rect.y1]
                                except:
                                    rect = [0, 0, 0, 0]  # Default coordinates
                                
                                field_info = {
                                    "page": page_number + 1,
                                    "field_name": field_name,
                                    "field_type": field_type,
                                    "rect": rect,
                                    "value": field_value,
                                    "label": self._get_appropriate_label(page, rect, field_name)
                                }
                                
                                all_fields[field_name] = field_info
                                total_count += 1
                                
                                extracted_label = field_info.get("label", "")
                                print(f"Found field: {field_name} (Type: {field_type}) -> '{extracted_label}' on page {page_number + 1}")
                                
                            except Exception as widget_error:
                                print(f"Error processing widget on page {page_number + 1}: {str(widget_error)}")
                                # Still count it but create a placeholder
                                placeholder_name = f"error_field_{page_number + 1}_{total_count}"
                                all_fields[placeholder_name] = {
                                    "page": page_number + 1,
                                    "field_name": placeholder_name,
                                    "field_type": -1,
                                    "rect": [0, 0, 0, 0],
                                    "value": ""
                                }
                                total_count += 1
                                continue
                
                    # Try alternative approach for this page - check annotations
                    try:
                        annotations = page.annots()
                        if annotations:
                            for annot in annotations:
                                if annot.type[1] == "Widget":  # Form field annotation
                                    try:
                                        annot_name = f"annot_{page_number + 1}_{total_count}"
                                        
                                        # Check if this field is already captured
                                        already_exists = False
                                        for existing_field in all_fields.values():
                                            if (existing_field["page"] == page_number + 1 and 
                                                abs(existing_field["rect"][0] - annot.rect.x0) < 1 and
                                                abs(existing_field["rect"][1] - annot.rect.y0) < 1):
                                                already_exists = True
                                                break
                                        
                                        if not already_exists:
                                            field_info = {
                                                "page": page_number + 1,
                                                "field_name": annot_name,
                                                "field_type": 7,  # Default to text type
                                                "rect": [annot.rect.x0, annot.rect.y0, annot.rect.x1, annot.rect.y1],
                                                "value": ""
                                            }
                                            all_fields[annot_name] = field_info
                                            total_count += 1
                                            print(f"Found additional field via annotation: {annot_name} on page {page_number + 1}")
                                    
                                    except Exception as annot_error:
                                        print(f"Error processing annotation on page {page_number + 1}: {str(annot_error)}")
                                        continue
                    except Exception as annot_error:
                        print(f"Error checking annotations on page {page_number + 1}: {str(annot_error)}")
                                
                except Exception as page_error:
                    print(f"Error processing page {page_number + 1}: {str(page_error)}")
                    continue
            
            result = {
                "fields": all_fields,
                "total_fields": total_count,
                "pages": total_pages
            }
            
            print(f"Extracted {total_count} fields from {total_pages} pages")
            return result
            
        except Exception as e:
            print(f"Error extracting form fields: {str(e)}")
            return {
                "error": str(e),
                "fields": {},
                "total_fields": 0,
                "pages": 0
            }
        finally:
            if doc is not None:
                doc.close()
    
    def get_field_coordinates(self, pdf_content: bytes, field_name: str) -> Optional[Dict[str, Any]]:
        """
        Get the coordinates of a specific field in the PDF
        """
        doc = None
        if fitz is None:
            raise HTTPException(
                status_code=501,
                detail="PDF field coordinate lookup temporarily disabled (PyMuPDF not installed)."
            )

        try:
            doc = fitz.open(stream=pdf_content, filetype="pdf")
            
            for page_number in range(len(doc)):
                page = doc[page_number]
                widgets = page.widgets()
                
                for widget in widgets:
                    if widget.field_name == field_name:
                        rect = widget.rect
                        center_x = (rect.x0 + rect.x1) / 2
                        center_y = (rect.y0 + rect.y1) / 2
                        width = rect.x1 - rect.x0
                        height = rect.y1 - rect.y0
                        
                        return {
                            "page": page_number + 1,
                            "rect": [rect.x0, rect.y0, rect.x1, rect.y1],
                            "center": [center_x, center_y],
                            "width": width,
                            "height": height
                        }
            
            return None
            
        except Exception as e:
            print(f"Error getting coordinates for field {field_name}: {str(e)}")
            return None
        finally:
            if doc is not None:
                doc.close()
    
    def prepare_fields_for_frontend(self, extracted_fields: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare extracted fields in a format suitable for frontend consumption
        """
        frontend_fields = {}
        
        if "fields" in extracted_fields:
            for field_name, field_data in extracted_fields["fields"].items():
                rect = field_data["rect"]
                
                # Calculate center coordinates for positioning
                center_x = (rect[0] + rect[2]) / 2
                center_y = (rect[1] + rect[3]) / 2
                width = rect[2] - rect[0]
                height = rect[3] - rect[1]
                
                frontend_fields[field_name] = {
                    "page": field_data["page"],
                    "type": field_data["field_type"],
                    "value": field_data.get("value", ""),
                    "label": field_data.get("label", field_name),  # Use extracted label
                    "position": {
                        "x": center_x,
                        "y": center_y,
                        "width": width,
                        "height": height
                    },
                    "rect": rect,
                    "editable": True
                }
        
        return {
            "formFields": frontend_fields,
            "metadata": {
                "total_fields": extracted_fields.get("total_fields", 0),
                "pages": extracted_fields.get("pages", 0),
                "extraction_method": "enhanced_pdf_fields"
            }
        }
    
    def _get_appropriate_label(self, page, field_rect, field_name):
        """
        Decide whether to extract a label from PDF text or use the field name as-is.
        Only extract labels for fields with confusing/generic names.
        """
        # Keywords that indicate a field needs better labeling
        confusing_keywords = [
            'untitled', 'unnamed', 'field_', 'text_', 'check_', 
            'button_', 'form_', 'widget_', 'annotation_', 'radio_'
        ]
        
        # Check if field name contains confusing keywords
        field_name_lower = field_name.lower()
        needs_better_label = any(keyword in field_name_lower for keyword in confusing_keywords)
        
        if needs_better_label:
            # Extract meaningful label from PDF text near field position
            extracted_label = self._extract_field_label(page, field_rect, field_name)
            return extracted_label if extracted_label else self._clean_field_name(field_name)
        else:
            # Use the original field name as is for meaningful names
            return field_name

    def _extract_field_label(self, page, field_rect, field_name):
        """
        Extract the text label associated with a form field by looking for nearby text
        
        Args:
            page: PyMuPDF page object
            field_rect: Rectangle coordinates of the form field
            field_name: Original field name
            
        Returns:
            Extracted label text or cleaned field name
        """
        try:
            # Get all text blocks on the page
            text_blocks = page.get_text("dict")
            
            # Field coordinates
            field_x0, field_y0, field_x1, field_y1 = field_rect
            field_center_x = (field_x0 + field_x1) / 2
            field_center_y = (field_y0 + field_y1) / 2
            
            best_label = ""
            min_distance = float('inf')
            
            # Look through all text blocks
            for block in text_blocks.get("blocks", []):
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    for span in line.get("spans", []):
                        text = span.get("text", "").strip()
                        if not text or len(text) < 2:
                            continue
                        
                        # Skip if text looks like field values or common form elements
                        if text.lower() in ['yes', 'no', 'x', '✓', '□', '☐', '☑', '✓']:
                            continue
                        
                        # Get text position
                        text_bbox = span.get("bbox", [0, 0, 0, 0])
                        text_x0, text_y0, text_x1, text_y1 = text_bbox
                        text_center_x = (text_x0 + text_x1) / 2
                        text_center_y = (text_y0 + text_y1) / 2
                        
                        # Calculate distance between text and field
                        distance = ((text_center_x - field_center_x) ** 2 + (text_center_y - field_center_y) ** 2) ** 0.5
                        
                        # Prefer text that's to the left or above the field (typical label positions)
                        if text_x1 <= field_x0 + 10:  # Text to the left
                            distance *= 0.8  # Prefer left labels
                        elif text_y1 <= field_y0 + 5:  # Text above
                            distance *= 0.9  # Prefer labels above
                        
                        # Only consider text that's reasonably close (within 200 pixels)
                        if distance < 200 and distance < min_distance:
                            # Clean up the text
                            cleaned_text = self._clean_label_text(text)
                            if cleaned_text and len(cleaned_text) > 1:
                                best_label = cleaned_text
                                min_distance = distance
            
            # If we found a good label, return it; otherwise return cleaned field name
            if best_label:
                return best_label
            else:
                return self._clean_field_name(field_name)
                
        except Exception as e:
            print(f"Error extracting label for field {field_name}: {str(e)}")
            return self._clean_field_name(field_name)
    
    def _clean_label_text(self, text):
        """Clean and normalize extracted label text"""
        # Remove common form artifacts
        text = text.replace(':', '').replace('_', ' ').strip()
        
        # Skip very short text or numbers only
        if len(text) < 2 or text.isdigit():
            return ""
        
        # Skip common non-label text
        skip_words = {'page', 'form', 'date', 'signature', 'print', 'please', 'check', 'fill'}
        if text.lower() in skip_words:
            return ""
        
        # Capitalize properly
        words = text.split()
        cleaned_words = []
        for word in words:
            if len(word) > 0:
                cleaned_words.append(word.capitalize())
        
        return ' '.join(cleaned_words) if cleaned_words else ""
    
    def _clean_field_name(self, field_name):
        """Convert field name to a readable label"""
        if not field_name:
            return "Unnamed Field"
        
        # Handle unnamed fields
        if field_name.startswith(('unnamed_field_', 'error_field_', 'annot_')):
            return "Form Field"
        
        # Clean up the field name
        cleaned = field_name.replace('_', ' ').replace('-', ' ')
        
        # Split and capitalize
        words = cleaned.split()
        capitalized = []
        for word in words:
            if word.isdigit():
                capitalized.append(f"#{word}")
            else:
                capitalized.append(word.capitalize())
        
        return ' '.join(capitalized) if capitalized else "Form Field"
