from fastapi import HTTPException

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

import io
import json
import time
import os
import re
from typing import Dict, Any, List, Tuple, Optional

class FieldExtractionService:
    """
    Service for extracting form fields and their coordinates from PDF files
    Replaces Gemini and Mistral services with direct PDF field extraction
    """
    
    def __init__(self):
        # Ensure debug log directory exists
        debug_log_dir = r'e:\codelink\project\joba\joba-backend\.cursor'
        try:
            os.makedirs(debug_log_dir, exist_ok=True)
        except Exception:
            pass  # Silently fail if directory can't be created
    
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
            # Track unique fields by name+position to detect true duplicates
            seen_positions = {}  # Maps (field_name, page, rect_hash) -> field_name used
            duplicates_skipped = 0
            widgets_processed = 0
            
            for page_number in range(total_pages):
                try:
                    page = doc[page_number]
                    widgets = page.widgets()
                    
                    if widgets:
                        for widget in widgets:
                            widgets_processed += 1
                            try:
                                field_name = widget.field_name
                                
                                if not field_name:
                                    # Generate a unique name for unnamed fields
                                    field_name = f"unnamed_field_{page_number + 1}_{total_count}"
                                
                                # Try to get coordinates safely (needed for duplicate detection)
                                try:
                                    rect = [widget.rect.x0, widget.rect.y0, widget.rect.x1, widget.rect.y1]
                                except:
                                    rect = [0, 0, 0, 0]  # Default coordinates
                                
                                # Create a position hash for duplicate detection (round to avoid floating point issues)
                                rect_hash = tuple(round(coord, 1) for coord in rect)
                                position_key = (field_name, page_number + 1, rect_hash)
                                
                                # Check if this is a true duplicate (same name, page, and position)
                                if position_key in seen_positions:
                                    # True duplicate - skip it
                                    existing_field_name = seen_positions[position_key]
                                    duplicates_skipped += 1
                                    continue
                                
                                # Handle duplicate field names by appending a counter (for radio buttons with same name but different positions)
                                original_name = field_name
                                counter = 1
                                while field_name in all_fields:
                                    field_name = f"{original_name}_{counter}"
                                    counter += 1
                                
                                # Mark this position as seen
                                seen_positions[position_key] = field_name
                                
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
                                
                                # First, try to get field_label from the widget (most accurate)
                                widget_label = None
                                try:
                                    widget_label = widget.field_label if hasattr(widget, 'field_label') and widget.field_label else None
                                except:
                                    pass
                                
                                # If widget has a field_label and it's different from field_name, use it
                                # Otherwise, extract label from nearby text
                                if widget_label and widget_label != field_name and len(widget_label.strip()) > 0:
                                    # Clean up the label - remove common format hints in parentheses
                                    extracted_label = self._clean_widget_label(widget_label)
                                else:
                                    extracted_label = self._get_appropriate_label(page, rect, field_name)
                                
                                field_info = {
                                    "page": page_number + 1,
                                    "field_name": field_name,
                                    "field_type": field_type,
                                    "rect": rect,
                                    "value": field_value,
                                    "label": extracted_label
                                }
                                
                                all_fields[field_name] = field_info
                                total_count += 1
                                
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
                    # Note: This is a fallback for fields not captured by widgets()
                    # We use the same position-based duplicate detection
                    try:
                        annotations = page.annots()
                        if annotations:
                            for annot in annotations:
                                if annot.type[1] == "Widget":  # Form field annotation
                                    try:
                                        # Get annotation field name if available
                                        annot_field_name = None
                                        try:
                                            annot_field_name = annot.field_name if hasattr(annot, 'field_name') and annot.field_name else None
                                        except:
                                            pass
                                        
                                        if not annot_field_name:
                                            annot_field_name = f"annot_{page_number + 1}_{total_count}"
                                        
                                        # Get coordinates
                                        annot_rect = [annot.rect.x0, annot.rect.y0, annot.rect.x1, annot.rect.y1]
                                        annot_rect_hash = tuple(round(coord, 1) for coord in annot_rect)
                                        annot_position_key = (annot_field_name, page_number + 1, annot_rect_hash)
                                        
                                        # Check if this annotation field is already captured (same position)
                                        if annot_position_key in seen_positions:
                                            # Already captured - skip
                                            continue
                                        
                                        # Also check if a field at this exact position already exists
                                        already_exists = False
                                        for existing_field in all_fields.values():
                                            if (existing_field["page"] == page_number + 1 and 
                                                abs(existing_field["rect"][0] - annot.rect.x0) < 2 and
                                                abs(existing_field["rect"][1] - annot.rect.y0) < 2 and
                                                abs(existing_field["rect"][2] - annot.rect.x1) < 2 and
                                                abs(existing_field["rect"][3] - annot.rect.y1) < 2):
                                                already_exists = True
                                                break
                                        
                                        if not already_exists:
                                            # Handle name collision
                                            final_annot_name = annot_field_name
                                            counter = 1
                                            while final_annot_name in all_fields:
                                                final_annot_name = f"{annot_field_name}_{counter}"
                                                counter += 1
                                            
                                            # Mark position as seen
                                            seen_positions[annot_position_key] = final_annot_name
                                            
                                            field_info = {
                                                "page": page_number + 1,
                                                "field_name": final_annot_name,
                                                "field_type": 7,  # Default to text type
                                                "rect": annot_rect,
                                                "value": ""
                                            }
                                            all_fields[final_annot_name] = field_info
                                            total_count += 1
                                            print(f"Found additional field via annotation: {final_annot_name} on page {page_number + 1}")
                                    
                                    except Exception as annot_error:
                                        print(f"Error processing annotation on page {page_number + 1}: {str(annot_error)}")
                                        continue
                    except Exception as annot_error:
                        print(f"Error checking annotations on page {page_number + 1}: {str(annot_error)}")
                                
                except Exception as page_error:
                    print(f"Error processing page {page_number + 1}: {str(page_error)}")
                    continue
            
            # Post-process: Group radio buttons and handle duplicate labels
            grouped_fields, radio_groups_merged = self._group_radio_buttons_and_deduplicate(all_fields)
            
            result = {
                "fields": grouped_fields,
                "total_fields": len(grouped_fields),
                "pages": total_pages
            }
            
            print(f"Extracted {len(grouped_fields)} fields from {total_pages} pages (after grouping radio buttons)")
            print(f"Statistics: {widgets_processed} widgets processed, {duplicates_skipped} duplicates skipped, {radio_groups_merged} radio groups merged")
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
    
    def _group_radio_buttons_and_deduplicate(self, all_fields: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        """
        Group radio buttons that share the same original field_name and handle duplicate labels.
        Radio buttons in PDFs share the same field_name but have different positions (Yes/No options).
        Returns: (grouped_fields_dict, number_of_radio_groups_merged)
        """
        grouped_fields = {}
        radio_groups_merged = 0  # Not used anymore since we keep all fields
        seen_labels = {}  # Track labels to detect duplicates
        
        # Add ALL fields including radio button variants (Yes/No options)
        # User wants both Yes and No fields to appear as separate checkboxes
        for field_name, field_data in all_fields.items():
            field_type = field_data.get("field_type", -1)
            label = field_data.get("label", field_name)
            
            # Check for duplicate labels (same label, different field)
            if label in seen_labels:
                # Duplicate label detected
                existing_field = seen_labels[label]
                # Keep both but log the duplicate (user said rarely any duplicate, so we keep them)
            else:
                seen_labels[label] = field_name
            
            # Add the field (including all radio button variants)
            grouped_fields[field_name] = field_data
        
        return grouped_fields, radio_groups_merged
    
    def _map_field_type_to_frontend(self, field_type: int, has_radio_group: bool = False) -> str:
        """
        Map PyMuPDF field type integer to frontend-friendly type string
        
        PyMuPDF field types:
        0 = PDF_WIDGET_TYPE_UNKNOWN
        1 = PDF_WIDGET_TYPE_BUTTON
        2 = PDF_WIDGET_TYPE_CHECKBOX
        3 = PDF_WIDGET_TYPE_COMBOBOX
        4 = PDF_WIDGET_TYPE_LISTBOX
        5 = PDF_WIDGET_TYPE_RADIOBUTTON
        6 = PDF_WIDGET_TYPE_SIGNATURE
        7 = PDF_WIDGET_TYPE_TEXT
        """
        type_mapping = {
            0: "unknown",
            1: "button",
            2: "checkbox",  # Checkbox
            3: "dropdown",  # ComboBox
            4: "listbox",    # ListBox
            5: "radio" if has_radio_group else "checkbox",  # RadioButton - use "radio" if grouped, else "checkbox"
            6: "signature", # Signature
            7: "text"       # Text field
        }
        return type_mapping.get(field_type, "text")
    
    def prepare_fields_for_frontend(self, extracted_fields: Dict[str, Any], pdf_content: bytes = None) -> Dict[str, Any]:
        """
        Prepare extracted fields in a format suitable for frontend consumption.
        Radio button groups are represented as a single field with an options array.
        
        Args:
            extracted_fields: Dictionary with extracted field data
            pdf_content: Optional PDF content bytes for extracting option labels from PDF text
        """
        frontend_fields = {}
        
        if "fields" in extracted_fields:
            # First pass: Identify radio button pairs and group them
            radio_pairs = {}  # Maps base_name -> {base_field, variant_fields}
            for field_name, field_data in extracted_fields["fields"].items():
                field_type = field_data.get("field_type", -1)
                if field_type == 5 and "_" in field_name:
                    base_name = field_name.rsplit("_", 1)[0]
                    if base_name in extracted_fields["fields"]:
                        base_field = extracted_fields["fields"][base_name]
                        if base_field.get("field_type", -1) == 5:
                            if base_name not in radio_pairs:
                                radio_pairs[base_name] = {"base": base_name, "variants": []}
                            radio_pairs[base_name]["variants"].append(field_name)
            
            # Track which fields are part of radio groups (to skip them in the main loop)
            radio_group_fields = set()
            for base_name in radio_pairs:
                radio_group_fields.add(base_name)
                radio_group_fields.update(radio_pairs[base_name]["variants"])
            
            # Open PDF if provided for extracting option labels from text
            doc = None
            pages_cache = {}  # Cache page objects by page number
            if pdf_content and fitz is not None:
                try:
                    doc = fitz.open(stream=pdf_content, filetype="pdf")
                except Exception as e:
                    doc = None
            
            # Process radio button groups first - create single field entry for each group
            for base_name in radio_pairs:
                base_field_data = extracted_fields["fields"][base_name]
                variants = radio_pairs[base_name]["variants"]
                
                # Get normalized label for the group
                base_label = base_field_data.get("label", base_name)
                normalized_label = self._normalize_radio_group_label(base_label)
                
                # Collect all radio button options with their positions
                radio_options = []
                
                # Process base field
                base_rect = base_field_data["rect"]
                base_center_x = (base_rect[0] + base_rect[2]) / 2
                base_center_y = (base_rect[1] + base_rect[3]) / 2
                base_page_num = base_field_data.get("page", 1)
                
                # Extract option label for base field - try PDF text extraction first
                option_label = None
                if doc and base_page_num <= len(doc):
                    try:
                        page = doc[base_page_num - 1]
                        extracted_option = self._extract_radio_option_label_from_page(page, base_rect, base_name, normalized_label)
                        # Validate extracted option - if invalid, reject it and use intelligent defaults
                        if extracted_option and variants:
                            variant_rect = extracted_fields["fields"][variants[0]]["rect"]
                            variant_center_x = (variant_rect[0] + variant_rect[2]) / 2
                            is_valid = self._validate_extracted_option(extracted_option, normalized_label, False, base_center_x, variant_center_x)
                            if is_valid:
                                option_label = extracted_option
                        else:
                            option_label = extracted_option
                    except Exception as e:
                        pass
                
                # Fallback to other methods if PDF extraction didn't work or was rejected
                if not option_label and variants:
                    variant_rect = extracted_fields["fields"][variants[0]]["rect"]
                    variant_center_x = (variant_rect[0] + variant_rect[2]) / 2
                    option_label = self._extract_radio_option_label(extracted_fields["fields"], base_name, base_rect, variants[0], variant_rect, normalized_label)
                    if not option_label:
                        option_label = self._get_intelligent_option_default(normalized_label, base_center_x, variant_center_x, is_variant=False)
                    if not option_label:
                        option_label = "Yes" if base_center_x < variant_center_x else "No"
                elif not option_label:
                    option_label = "Yes"
                
                radio_options.append({
                    "value": option_label,
                    "label": option_label,
                    "position": {
                        "x": base_center_x,
                        "y": base_center_y,
                        "width": base_rect[2] - base_rect[0],
                        "height": base_rect[3] - base_rect[1]
                    },
                    "rect": base_rect,
                    "field_name": base_name
                })
                
                # Process variant fields
                for variant_name in variants:
                    variant_field_data = extracted_fields["fields"][variant_name]
                    variant_rect = variant_field_data["rect"]
                    variant_center_x = (variant_rect[0] + variant_rect[2]) / 2
                    variant_center_y = (variant_rect[1] + variant_rect[3]) / 2
                    variant_page_num = variant_field_data.get("page", 1)
                    
                    # Extract option label for variant - try PDF text extraction first
                    option_label = None
                    if doc and variant_page_num <= len(doc):
                        try:
                            page = doc[variant_page_num - 1]
                            extracted_option = self._extract_radio_option_label_from_page(page, variant_rect, variant_name, normalized_label)
                            # Validate extracted option - if invalid, reject it and use intelligent defaults
                            if extracted_option:
                                is_valid = self._validate_extracted_option(extracted_option, normalized_label, True, variant_center_x, base_center_x)
                                if is_valid:
                                    option_label = extracted_option
                            else:
                                option_label = extracted_option
                        except Exception as e:
                            pass
                    
                    # Fallback to other methods if PDF extraction didn't work or was rejected
                    if not option_label:
                        option_label = self._extract_radio_option_label(extracted_fields["fields"], variant_name, variant_rect, base_name, base_rect, normalized_label)
                        if not option_label:
                            option_label = self._get_intelligent_option_default(normalized_label, variant_center_x, base_center_x, is_variant=True)
                        if not option_label:
                            option_label = "No" if variant_center_x > base_center_x else "Yes"
                    
                    radio_options.append({
                        "value": option_label,
                        "label": option_label,
                        "position": {
                            "x": variant_center_x,
                            "y": variant_center_y,
                            "width": variant_rect[2] - variant_rect[0],
                            "height": variant_rect[3] - variant_rect[1]
                        },
                        "rect": variant_rect,
                        "field_name": variant_name
                    })
                
                # Sort options by x position (left to right)
                radio_options.sort(key=lambda opt: opt["position"]["x"])
                
                # Check for duplicate options and fix them using intelligent defaults
                # Normalize labels for comparison (e.g., "C Section" = "C-Section")
                def normalize_for_comparison(label: str) -> str:
                    """Normalize label for duplicate detection"""
                    if not label:
                        return label
                    normalized = label.lower().strip()
                    # Normalize variations
                    normalized = normalized.replace('c section', 'c-section')
                    normalized = normalized.replace('cesarean', 'c-section')
                    normalized = normalized.replace('cesarian', 'c-section')
                    return normalized
                
                option_labels = [opt["label"] for opt in radio_options]
                normalized_labels = [normalize_for_comparison(label) for label in option_labels]
                
                if len(set(normalized_labels)) < len(normalized_labels):
                    # We have duplicates (after normalization) - need to fix them
                    # Re-generate ALL options using intelligent defaults to ensure distinct values
                    for idx, opt in enumerate(radio_options):
                        is_variant = idx > 0
                        other_center_x = radio_options[1 - idx]["position"]["x"] if len(radio_options) > 1 else opt["position"]["x"]
                        intelligent_default = self._get_intelligent_option_default(normalized_label, opt["position"]["x"], other_center_x, is_variant)
                        if intelligent_default:
                            opt["value"] = intelligent_default
                            opt["label"] = intelligent_default
                        elif len(radio_options) == 2:
                            # Fallback: ensure we have Yes/No or distinct values
                            if idx == 0:
                                opt["value"] = "Yes"
                                opt["label"] = "Yes"
                            else:
                                opt["value"] = "No"
                                opt["label"] = "No"
                
                # Create single field entry for the radio group
                # Use the base field's position as the group position
                group_center_x = (base_rect[0] + base_rect[2]) / 2
                group_center_y = (base_rect[1] + base_rect[3]) / 2
                
                radio_group_field = {
                    "page": base_field_data["page"],
                    "type": "radio",
                    "inputType": "radio",
                    "raw_type": 5,
                    "value": base_field_data.get("value", ""),
                    "label": normalized_label,
                    "options": radio_options,  # Array of all radio button options
                    "position": {
                        "x": group_center_x,
                        "y": group_center_y,
                        "width": base_rect[2] - base_rect[0],
                        "height": base_rect[3] - base_rect[1]
                    },
                    "rect": base_rect,
                    "editable": True,
                    "radioGroup": base_name,
                    "name": base_name
                }
                
                # Use the base field name as the key
                frontend_fields[base_name] = radio_group_field
            
            # Process non-radio fields (skip fields that are part of radio groups)
            for field_name, field_data in extracted_fields["fields"].items():
                # Skip if this field is part of a radio group (we already processed it above)
                if field_name in radio_group_fields:
                    continue
                rect = field_data["rect"]
                
                # Calculate center coordinates for positioning
                center_x = (rect[0] + rect[2]) / 2
                center_y = (rect[1] + rect[3]) / 2
                width = rect[2] - rect[0]
                height = rect[3] - rect[1]
                
                # Get field type
                raw_field_type = field_data["field_type"]
                
                # Get base label
                base_label = field_data.get("label", field_name)
                final_label = base_label
                
                # Map field type to frontend-friendly string
                frontend_type = self._map_field_type_to_frontend(raw_field_type, has_radio_group=False)
                
                field_obj = {
                    "page": field_data["page"],
                    "type": frontend_type,  # Use mapped type string
                    "inputType": frontend_type,  # Also provide as inputType for frontend compatibility
                    "raw_type": raw_field_type,  # Keep original for reference
                    "value": field_data.get("value", ""),
                    "label": final_label,
                    "position": {
                        "x": center_x,
                        "y": center_y,
                        "width": width,
                        "height": height
                    },
                    "rect": rect,
                    "editable": True
                }
                
                frontend_fields[field_name] = field_obj
        
        # Close PDF if opened
        if doc is not None:
            doc.close()
        
        return {
            "formFields": frontend_fields,
            "metadata": {
                "total_fields": extracted_fields.get("total_fields", 0),
                "pages": extracted_fields.get("pages", 0),
                "extraction_method": "enhanced_pdf_fields"
            }
        }
    
    def _clean_widget_label(self, label):
        """
        Clean up widget field_label by removing common format hints in parentheses
        Examples:
        - "Date of Birth (dd/mm/yyyy)" -> "Date of Birth"
        - "Home Phone Number (+ Area Code)" -> "Home Phone Number"
        - "Plan Member/Employee Name (Last, First, Middle Initial)" -> "Plan Member/Employee Name"
        """
        if not label:
            return label
        
        # Remove common format hints in parentheses at the end
        # Pattern: text (format hint) -> text
        # Match parentheses at the end that contain format hints
        format_patterns = [
            r'\s*\(dd/mm/yyyy\)\s*$',
            r'\s*\(mm/dd/yyyy\)\s*$',
            r'\s*\(yyyy-mm-dd\)\s*$',
            r'\s*\(\+?\s*Area\s+Code\)\s*$',
            r'\s*\(Last,\s*First,\s*Middle\s+Initial\)\s*$',
            r'\s*\(Street,\s*City,\s*Province,\s*Postal\s+Code\)\s*$',
        ]
        
        cleaned = label
        for pattern in format_patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        # Also remove trailing colons and extra whitespace
        cleaned = cleaned.rstrip(':').strip()
        
        return cleaned if cleaned else label
    
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
        
        # Check if field name contains confusing keywords OR is purely numeric
        field_name_lower = field_name.lower()
        is_numeric = field_name.isdigit() or (field_name.replace('_', '').replace('-', '').isdigit())
        needs_better_label = any(keyword in field_name_lower for keyword in confusing_keywords) or is_numeric
        
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
            candidate_count = 0
            
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
                        
                        # Get text position first (needed for smart filtering)
                        text_bbox = span.get("bbox", [0, 0, 0, 0])
                        text_x0, text_y0, text_x1, text_y1 = text_bbox
                        text_center_x = (text_x0 + text_x1) / 2
                        text_center_y = (text_y0 + text_y1) / 2
                        
                        # Determine text position relative to field
                        is_left = text_x1 <= field_x0 + 20  # Text to the left (increased tolerance)
                        is_above = text_y1 <= field_y0 + 15  # Text above (increased tolerance)
                        # Check if text is horizontally aligned with field (same row)
                        # Text should be within the field's vertical range or very close
                        is_horizontal_aligned = (text_y0 >= field_y0 - 10 and text_y1 <= field_y1 + 10) or abs(text_center_y - field_center_y) < 15
                        # Check if text is on the same row (more strict)
                        is_same_row = abs(text_center_y - field_center_y) < 10
                        
                        # Skip placeholder/hint text patterns, but be less aggressive for left labels
                        # (left labels are more likely to be actual field labels)
                        if not is_left:  # Only filter aggressively if text is NOT to the left
                            if self._is_placeholder_text(text):
                                continue
                        else:
                            # For left labels, only filter obvious placeholders
                            if self._is_obvious_placeholder(text):
                                continue
                        
                        # Filter out instruction text and section headers (not field labels)
                        text_lower = text.lower().strip()
                        instruction_indicators = [
                            'to be completed', 'please', 'note:', 'i authorize', 'i acknowledge',
                            'i confirm', 'this consent', 'the patient', 'consultation reports',
                            'for the purpose', 'refusing to consent', 'may be revoked',
                            'photocopy or electronic', 'as valid as', 'excludes genetic'
                        ]
                        if any(indicator in text_lower for indicator in instruction_indicators):
                            continue
                        
                        # Calculate distance between text and field
                        distance = ((text_center_x - field_center_x) ** 2 + (text_center_y - field_center_y) ** 2) ** 0.5
                        
                        # Calculate raw distance first
                        raw_distance = distance
                        
                        # Strongly prefer labels that are on the same row and to the left
                        # This ensures we get the correct label for each field
                        if is_left and is_same_row:
                            # Perfect match: left and same row - this is almost certainly the correct label
                            if raw_distance < 200:
                                distance *= 0.05  # Extremely strongly prefer same-row left labels
                            else:
                                distance *= 0.2
                        elif is_left and is_horizontal_aligned:
                            # Good match: left and horizontally aligned
                            if raw_distance < 150:
                                distance *= 0.1  # Very strongly prefer close left labels
                            else:
                                distance *= 0.3  # Still prefer left labels, but less aggressively for distant ones
                        elif is_left:
                            # Left but not aligned - might belong to another field
                            if raw_distance < 100:
                                distance *= 0.2  # Prefer if very close
                            else:
                                distance *= 0.5  # Less preference for distant unaligned left labels
                        elif is_above:
                            if raw_distance < 100:
                                distance *= 0.4  # Prefer labels above if close
                            else:
                                distance *= 0.7  # Less preference for distant labels above
                        elif is_horizontal_aligned:
                            distance *= 0.8  # Slightly prefer horizontally aligned
                        else:
                            # Text to the right or below is less likely to be a label
                            distance *= 2.0  # Heavily penalize text to the right/below
        
                        # Filter out very long text (likely section headers or paragraphs, not field labels)
                        # Field labels are typically short (1-5 words)
                        word_count = len(text.split())
                        if word_count > 8:  # Skip very long text (likely section headers)
                            continue
                        
                        # Increase search radius to 300 pixels for better coverage
                        if distance < 300:
                            candidate_count += 1
                            # Clean up the text
                            cleaned_text = self._clean_label_text(text)
                            if cleaned_text and len(cleaned_text) > 1 and distance < min_distance:
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
    
    def _is_obvious_placeholder(self, text):
        """
        Check if text is an obvious placeholder (date formats, area code hints, etc.)
        Used for left labels where we want to be less aggressive
        """
        text_lower = text.lower().strip()
        
        # Obvious date format patterns
        if any(pattern in text_lower for pattern in ['dd/mm/yyyy', 'mm/dd/yyyy', 'yyyy-mm-dd', '(dd', '(mm', 'dd-mm-yyyy']):
            return True
        
        # Obvious area code patterns
        if any(pattern in text_lower for pattern in ['+ area code', '+ area', 'area code']):
            return True
        
        return False
    
    def _is_placeholder_text(self, text):
        """
        Check if text looks like placeholder/hint text rather than an actual label
        Returns True if text should be skipped
        """
        text_lower = text.lower().strip()
        
        # Skip text that's entirely in parentheses (often hints/placeholders)
        if text.strip().startswith('(') and text.strip().endswith(')'):
            # But allow some exceptions like "(Street, City, Province, Postal Code)" which might be labels
            if len(text) > 50:  # Long parenthetical text might be a label
                return False
            # Common placeholder patterns
            placeholder_patterns = [
                'dd/mm/yyyy', 'mm/dd/yyyy', 'yyyy-mm-dd', 'dd-mm-yyyy',
                '+ area code', 'area code', '+ area',
                'last, first', 'first, last', 'last, first, middle',
                'street, city', 'city, province', 'postal code',
                'yes/no', 'check', 'select', 'choose', 'enter', 'fill',
                'optional', 'required', 'please', 'note:', 'note'
            ]
            for pattern in placeholder_patterns:
                if pattern in text_lower:
                    return True
            # If it's short and in parentheses, likely a placeholder
            if len(text) < 30:
                return True
        
        # Skip date format patterns
        if any(pattern in text_lower for pattern in ['dd/mm/yyyy', 'mm/dd/yyyy', 'yyyy-mm-dd', '(dd', '(mm']):
            return True
        
        # Skip instruction text
        instruction_keywords = [
            'if yes', 'if applicable', 'please', 'note:', 'note that',
            'this document', 'use the', 'from a form', 'responsible for',
            'completion of', 'related to'
        ]
        if any(keyword in text_lower for keyword in instruction_keywords):
            return True
        
        # Skip very short text that's just punctuation or numbers
        if len(text.strip()) <= 3 and (text.strip() in ['#', '+', '-', ':', '(', ')'] or text.strip().isdigit()):
            return True
        
        return False
    
    def _clean_label_text(self, text):
        """Clean and normalize extracted label text"""
        # Remove common form artifacts
        text = text.replace(':', '').replace('_', ' ').replace('-', ' ').strip()
        
        # Skip very short text (but allow single meaningful words like "Name", "Age")
        if len(text) < 2:
            return ""
        
        # Skip if text is purely numeric (but allow text with numbers like "Field 1")
        if text.isdigit() or (text.replace(' ', '').isdigit()):
            return ""
        
        # Skip common non-label text (but be less aggressive)
        skip_words = {'page', 'form', 'print', 'please', 'check', 'fill', 'sign'}
        if text.lower().strip() in skip_words and len(text.split()) == 1:
            return ""
        
        # Capitalize properly
        words = text.split()
        cleaned_words = []
        for word in words:
            if len(word) > 0:
                # Preserve common acronyms and proper nouns
                if word.isupper() and len(word) > 1:
                    cleaned_words.append(word)
                else:
                    cleaned_words.append(word.capitalize())
        
        result = ' '.join(cleaned_words) if cleaned_words else ""
        return result
    
    def _extract_radio_option_label(self, all_fields: Dict[str, Any], field_name: str, field_rect: List[float], 
                                     other_field_name: str, other_field_rect: List[float], group_label: str = None) -> Optional[str]:
        """
        Extract or infer the actual option label (e.g., "Male", "Female") for a radio button.
        This tries intelligent defaults first, then infers from field labels.
        
        Args:
            all_fields: Dictionary of all extracted fields
            field_name: Name of the current radio button field
            field_rect: Rectangle coordinates of the current radio button
            other_field_name: Name of the other radio button in the group (for context)
            other_field_rect: Rectangle coordinates of the other radio button
            group_label: The normalized label of the radio group (e.g., "Gender")
            
        Returns:
            Inferred option label (e.g., "Male", "Female") or None if not found
        """
        try:
            # Get field data
            field_data = all_fields.get(field_name, {})
            other_field_data = all_fields.get(other_field_name, {})
            
            field_label = field_data.get("label", "").lower().strip()
            other_field_label = other_field_data.get("label", "").lower().strip()
            
            # Calculate positions for intelligent defaults
            field_center_x = (field_rect[0] + field_rect[2]) / 2
            other_center_x = (other_field_rect[0] + other_field_rect[2]) / 2
            is_variant = "_" in field_name
            
            # FIRST: Try intelligent defaults based on group label (highest priority)
            if group_label:
                intelligent_default = self._get_intelligent_option_default(
                    group_label, field_center_x, other_center_x, is_variant
                )
                if intelligent_default:
                    return intelligent_default
            
            # SECOND: Check if label contains common option words
            common_options_map = {
                'male': 'Male',
                'female': 'Female',
                'yes': 'Yes',
                'no': 'No',
                'true': 'True',
                'false': 'False',
                'married': 'Married',
                'single': 'Single',
                'divorced': 'Divorced',
                'widowed': 'Widowed',
                'agree': 'Agree',
                'disagree': 'Disagree'
            }
            
            for option_key, option_value in common_options_map.items():
                if option_key in field_label:
                    return option_value
            
            # THIRD: Try to extract from label suffix (e.g., "gender one" -> "One")
            # But skip this if it would result in meaningless values like "_1"
            base_words = ['gender', 'field', 'option', 'choice', 'select']
            for base_word in base_words:
                if field_label.startswith(base_word):
                    remaining = field_label[len(base_word):].strip()
                    # Skip if remaining is just a number or underscore (not meaningful)
                    if remaining and len(remaining) < 20 and not (remaining.startswith('_') and remaining[1:].isdigit()):
                        # Capitalize the remaining text
                        option = remaining.title()
                        return option
            
            return None
            
        except Exception as e:
            return None
    
    def _validate_extracted_option(self, extracted_option: str, group_label: str, is_variant: bool, center_x: float, other_center_x: float) -> bool:
        """
        Validate if an extracted option makes sense for the given radio group AND position.
        Returns True if valid, False if should be rejected and use intelligent defaults instead.
        
        Args:
            extracted_option: The option label extracted from PDF
            group_label: The normalized label of the radio group
            is_variant: True if this is the variant (second) radio button, False if base (first)
            center_x: X coordinate of current radio button
            other_center_x: X coordinate of other radio button in group
            
        Returns:
            True if option is valid for this position, False if should be rejected
        """
        if not extracted_option or not group_label:
            return False
        
        extracted_lower = extracted_option.lower().strip()
        group_label_lower = group_label.lower().strip()
        
        # Childbirth - base should be "Vaginal", variant should be "C-Section"
        if 'childbirth' in group_label_lower or 'delivery' in group_label_lower or 'birth' in group_label_lower:
            vaginal_options = ['vaginal']
            csection_options = ['c-section', 'c section', 'cesarean', 'cesarian']
            
            if is_variant:
                # Variant should be C-Section
                if extracted_lower in csection_options:
                    return True
            else:
                # Base should be Vaginal
                if extracted_lower in vaginal_options:
                    return True
            
            # If extracted doesn't match expected position, reject it
            return False
        
        # Yes/No questions - both positions can be Yes or No, but we'll validate later for duplicates
        yes_no_keywords = [
            'accident', 'auto accident', 'automobile accident',
            'hospitalization', 'hospital', 'hospitalized',
            'occupational', 'illness', 'injury', 'work related',
            'disability', 'claim', 'benefit', 'coverage',
            'smoking', 'tobacco', 'alcohol', 'drug',
            'pregnancy', 'pregnant', 'allergy', 'allergic',
            'agree', 'consent', 'authorize', 'confirm', 'accept',
            'treated', 'condition', 'following', 'recommended', 'treatment'
        ]
        if any(word in group_label_lower for word in yes_no_keywords):
            valid_options = ['yes', 'no']
            if extracted_lower in valid_options:
                return True
            # If extracted doesn't match, reject it
            return False
        
        # For other groups, accept the extracted option
        return True
    
    def _get_intelligent_option_default(self, group_label: str, center_x: float, other_center_x: float, is_variant: bool) -> Optional[str]:
        """
        Get intelligent default option labels based on the group label.
        For example, "Gender" -> "Male"/"Female", "Marital Status" -> "Married"/"Single", etc.
        
        Args:
            group_label: The normalized label of the radio group (e.g., "Gender")
            center_x: X coordinate of current radio button
            other_center_x: X coordinate of other radio button in group
            is_variant: True if this is the variant (second) radio button, False if base (first)
            
        Returns:
            Option label or None if no intelligent default available
        """
        if not group_label:
            return None
        
        group_label_lower = group_label.lower().strip()
        
        # Gender field - use Male/Female
        if 'gender' in group_label_lower or 'sex' in group_label_lower:
            if is_variant:
                return "Female" if center_x > other_center_x else "Male"
            else:
                return "Male" if center_x < other_center_x else "Female"
        
        # Marital status
        if 'marital' in group_label_lower or 'marriage' in group_label_lower:
            if is_variant:
                return "Single" if center_x > other_center_x else "Married"
            else:
                return "Married" if center_x < other_center_x else "Single"
        
        # Childbirth - use Vaginal/C-Section
        if 'childbirth' in group_label_lower or 'delivery' in group_label_lower or 'birth' in group_label_lower:
            if is_variant:
                return "C-Section" if center_x > other_center_x else "Vaginal"
            else:
                return "Vaginal" if center_x < other_center_x else "C-Section"
        
        # Yes/No questions - handle many common patterns
        yes_no_keywords = [
            'agree', 'consent', 'authorize', 'confirm', 'accept',
            'accident', 'auto accident', 'automobile accident',
            'hospitalization', 'hospital', 'hospitalized',
            'occupational', 'illness', 'injury', 'work related',
            'disability', 'claim', 'benefit', 'coverage',
            'smoking', 'tobacco', 'alcohol', 'drug',
            'pregnancy', 'pregnant', 'allergy', 'allergic'
        ]
        if any(word in group_label_lower for word in yes_no_keywords):
            if is_variant:
                return "No" if center_x > other_center_x else "Yes"
            else:
                return "Yes" if center_x < other_center_x else "No"
        
        return None
    
    def _normalize_radio_group_label(self, label: str) -> str:
        """
        Normalize radio group label by removing common suffixes that indicate variants.
        Examples:
        - "Gender One" -> "Gender"
        - "Gender 1" -> "Gender"
        - "gender one" -> "Gender"
        - "Field 1" -> "Field"
        """
        if not label:
            return label
        
        # Remove common suffix patterns
        import re
        # Pattern: word followed by " one", " 1", " one ", etc.
        patterns = [
            r'\s+one\s*$',  # " one" at the end
            r'\s+1\s*$',    # " 1" at the end
            r'\s+first\s*$',  # " first" at the end
            r'_\d+\s*$',    # "_1", "_2" at the end
        ]
        
        normalized = label
        for pattern in patterns:
            normalized = re.sub(pattern, '', normalized, flags=re.IGNORECASE)
        
        # Clean up and capitalize properly
        normalized = normalized.strip()
        if normalized:
            # Capitalize first letter of each word
            words = normalized.split()
            capitalized = [word.capitalize() for word in words]
            normalized = ' '.join(capitalized)
        
        return normalized if normalized else label
    
    def _extract_radio_option_label_from_page(self, page, field_rect: List[float], field_name: str, group_label: str = None) -> Optional[str]:
        """
        Extract the actual option label from PDF text near a radio button position.
        This looks for text to the right of the radio button.
        
        Args:
            page: PyMuPDF page object
            field_rect: Rectangle coordinates [x0, y0, x1, y1] of the radio button
            field_name: Name of the field (for logging)
            group_label: The normalized label of the radio group (for context filtering)
            
        Returns:
            Extracted option label (e.g., "Male", "Female") or None if not found
        """
        try:
            # Get all text blocks on the page
            text_blocks = page.get_text("dict")
            
            # Field coordinates
            field_x0, field_y0, field_x1, field_y1 = field_rect
            field_center_x = (field_x0 + field_x1) / 2
            field_center_y = (field_y0 + field_y1) / 2
            
            best_label = None
            min_distance = float('inf')
            
            # Common radio button option patterns
            common_options = {
                'male', 'female', 'yes', 'no', 'true', 'false', 
                'married', 'single', 'divorced', 'widowed',
                'agree', 'disagree', 'accept', 'reject',
                'on', 'off', 'enabled', 'disabled',
                'active', 'inactive', 'present', 'absent',
                'full', 'part', 'partial', 'complete',
                'high', 'low', 'medium', 'normal',
                'good', 'bad', 'excellent', 'poor',
                'first', 'second', 'third', 'last',
                'beginner', 'intermediate', 'advanced',
                'primary', 'secondary', 'tertiary',
                'vaginal', 'c-section', 'c section', 'cesarean'
            }
            
            # Filter out text that looks like date formats, field labels, or instructions
            excluded_patterns = [
                'dd/mm/yyyy', 'mm/dd/yyyy', 'yyyy-mm-dd', 'dd-mm-yyyy',
                'dd/mm', 'mm/dd', 'yyyy', 'dd', 'mm',
                'area code', '+ area', 'phone', 'fax',
                'last, first', 'first, last', 'street, city',
                'is/was', 'patient', 'had day', 'surgery',
                'hospitalization', 'occupational', 'illness/injury'
            ]
            
            # Look through all text blocks
            for block in text_blocks.get("blocks", []):
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    for span in line.get("spans", []):
                        text = span.get("text", "").strip()
                        if not text or len(text) < 2:
                            continue
                        
                        # Get text position
                        text_bbox = span.get("bbox", [0, 0, 0, 0])
                        text_x0, text_y0, text_x1, text_y1 = text_bbox
                        text_center_x = (text_x0 + text_x1) / 2
                        text_center_y = (text_y0 + text_y1) / 2
                        
                        # Radio button option labels are typically:
                        # 1. To the right of the radio button (or very close horizontally)
                        # 2. On the same row (horizontally aligned)
                        # 3. Close to the radio button
                        is_to_right = text_x0 >= field_x1 - 10  # Text starts at or after radio button end (with tolerance)
                        is_same_row = abs(text_center_y - field_center_y) < 15  # Same vertical position (increased tolerance)
                        is_close = abs(text_center_x - field_center_x) < 150  # Within 150 pixels horizontally (increased range)
                        
                        # Also consider text that's slightly above/below but very close horizontally
                        is_vertically_close = abs(text_center_y - field_center_y) < 25
                        is_horizontally_aligned = abs(text_center_x - field_center_x) < 80
                        
                        if (is_to_right and is_same_row and is_close) or (is_horizontally_aligned and is_vertically_close and is_to_right):
                            # Clean the text
                            cleaned_text = self._clean_label_text(text)
                            if cleaned_text and len(cleaned_text) > 0:
                                text_lower = cleaned_text.lower()
                                
                                # Skip if text matches excluded patterns (date formats, field labels, etc.)
                                is_excluded = any(pattern in text_lower for pattern in excluded_patterns)
                                if is_excluded:
                                    continue
                                
                                # Skip if it's too long (likely not an option label)
                                if len(cleaned_text.split()) > 3:
                                    continue
                                
                                # Skip if text contains date-like patterns or looks like a field label
                                if any(char.isdigit() and '/' in cleaned_text for char in cleaned_text):
                                    # Looks like a date format
                                    continue
                                
                                # Prefer common option words, but also accept short meaningful text
                                is_common_option = text_lower in common_options
                                is_short_meaningful = len(cleaned_text.split()) <= 2 and len(cleaned_text) < 30
                                
                                # Additional validation: if group_label is provided, ensure extracted text makes sense
                                if group_label:
                                    group_label_lower = group_label.lower()
                                    # If group is about childbirth, prefer vaginal/c-section
                                    if 'childbirth' in group_label_lower or 'delivery' in group_label_lower:
                                        if text_lower not in ['vaginal', 'c-section', 'c section', 'cesarean', 'yes', 'no']:
                                            continue
                                    # If group is yes/no question, prefer yes/no
                                    elif any(word in group_label_lower for word in ['accident', 'hospitalization', 'occupational', 'illness', 'injury']):
                                        if text_lower not in ['yes', 'no']:
                                            continue
                                
                                if is_common_option or is_short_meaningful:
                                    distance = abs(text_center_x - field_center_x) + abs(text_center_y - field_center_y) * 0.5
                                    if distance < min_distance:
                                        best_label = cleaned_text
                                        min_distance = distance
            
            return best_label
            
        except Exception as e:
            return None
    
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
