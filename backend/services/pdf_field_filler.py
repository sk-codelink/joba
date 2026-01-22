from dataclasses import field
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
            
            # Print all radio button fields before processing
            self._print_radio_fields(doc)
            
            form_fields = form_data.get("formFields", {})
            filled_count = 0
            print(form_fields,"Form fields")
            for field_name, field_data in form_fields.items():
                value = field_data.get("value", "")
                # radio = field_data.get("field_name", "")
                
                if not value:
                    continue
                
                # Try to fill the form field directly first
                if self._fill_form_field_directly(doc, field_name, value):
                    filled_count += 1
                    # if radio:
                    #     print(f"Filled form field directly: {radio} = {value}")
                    # else:
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
            # For radio buttons, we need to collect all widgets in the group first
            # Store metadata instead of widget objects to avoid weak reference issues
            radio_widgets = []
            target_value = str(value)
            found_any_field = False
            
            # First pass: collect widget metadata (not widget objects) while pages are in scope
            for page_num in range(len(doc)):
                page = doc[page_num]
                widget_list = list(page.widgets())  # Convert to list to avoid iterator issues
                
                for widget_idx, widget in enumerate(widget_list):
                    if widget.field_name == field_name:
                        found_any_field = True
                        field_type = widget.field_type
                        
                        # Collect radio button widgets for batch processing
                        if field_type == 5:  # PDF_WIDGET_TYPE_RADIOBUTTON
                            # Store metadata while widget is still accessible
                            rect = widget.rect
                            try:
                                on_state = widget.on_state()
                            except:
                                on_state = None
                            
                            try:
                                button_states = widget.button_states()
                            except:
                                button_states = None
                            
                            radio_widgets.append({
                                'page': page_num,
                                'widget_idx': widget_idx,  # Store index to re-access widget
                                'x': rect.x0,
                                'y': rect.y0,
                                'on_state': on_state,  # Store on_state while accessible
                                'button_states': button_states  # Store button_states while accessible
                            })
                        else:
                            # Handle non-radio fields immediately
                            # Text fields
                            if field_type == 7:  # PDF_WIDGET_TYPE_TEXT
                                widget.field_value = str(value)
                            # Button / Checkbox
                            elif field_type in [1, 2]:  # Button / Checkbox field
                                if isinstance(value, bool):
                                    widget.field_value = "Yes" if value else "Off"
                                elif str(value).lower() in ['true', '1', 'yes', 'on']:
                                    widget.field_value = "Yes"
                                else:
                                    widget.field_value = "Off"
                            # Fallback: try to set as string
                            else:
                                widget.field_value = str(value)
                            
                            widget.update()
                            return True
            
            # Second pass: handle radio buttons as a group
            if radio_widgets:
                # Sort radio widgets by page first, then by x position (left to right), then by y position (top to bottom)
                # This matches the order that frontend sends options
                radio_widgets.sort(key=lambda w: (w['page'], w['x'], w['y']))
                
                # Debug: Print sorted radio widgets
                print(f"\n🔘 Processing radio group '{field_name}' with {len(radio_widgets)} options:")
                for idx, widget_info in enumerate(radio_widgets):
                    on_state = widget_info.get('on_state')
                    print(f"   [{idx}] Page {widget_info['page'] + 1}, Pos: ({widget_info['x']:.1f}, {widget_info['y']:.1f}), On State: {on_state}")
                
                matched = False
                
                # Try to parse target_value as index (frontend sends "0", "1", "2", etc.)
                try:
                    target_index = int(target_value)
                    # If it's a valid index, use index-based selection
                    if 0 <= target_index < len(radio_widgets):
                        # First, set all radio buttons to "Off" to ensure clean state
                        # This is crucial for multi-page radio groups
                        for idx, widget_info in enumerate(radio_widgets):
                            page_num = widget_info['page']
                            widget_idx = widget_info['widget_idx']
                            
                            try:
                                # Re-access the widget from the page
                                page = doc[page_num]
                                widget_list = list(page.widgets())
                                if widget_idx < len(widget_list):
                                    widget = widget_list[widget_idx]
                                    
                                    # Use stored button_states or default to "Off"
                                    button_states = widget_info.get('button_states')
                                    off_value = "Off"  # Default off value
                                    
                                    # button_states structure: {'normal': ['OnState'], 'down': ['Off', 'OnState']}
                                    # The "Off" value is typically in the 'down' key
                                    if button_states and isinstance(button_states, dict):
                                        # Check 'down' key first (usually has Off)
                                        if 'down' in button_states and isinstance(button_states['down'], list):
                                            if "Off" in button_states['down']:
                                                off_value = "Off"
                                        else:
                                            # Fallback: check all keys for "Off"
                                            for state_values in button_states.values():
                                                if isinstance(state_values, list) and "Off" in state_values:
                                                    off_value = "Off"
                                                    break
                                    
                                    widget.field_value = off_value
                                    widget.update()
                            except Exception as e:
                                print(f"⚠️ Warning setting widget[{idx}] to Off: {str(e)}")
                                # Try fallback: re-access and set to False
                                try:
                                    page = doc[widget_info['page']]
                                    widget_list = list(page.widgets())
                                    if widget_info['widget_idx'] < len(widget_list):
                                        widget = widget_list[widget_info['widget_idx']]
                                        widget.field_value = False
                                        widget.update()
                                except:
                                    pass
                        
                        # Now set the selected radio button to its "On" state
                        selected_widget_info = radio_widgets[target_index]
                        page_num = selected_widget_info['page']
                        widget_idx = selected_widget_info['widget_idx']
                        
                        try:
                            # Re-access the selected widget from the page
                            page = doc[page_num]
                            widget_list = list(page.widgets())
                            if widget_idx < len(widget_list):
                                selected_widget = widget_list[widget_idx]
                                
                                # Use stored on_state or button_states
                                on_state = selected_widget_info.get('on_state')
                                button_states = selected_widget_info.get('button_states')
                                
                                # Determine the correct "On" value
                                # Priority: use stored on_state, then try button_states, then fallback to True
                                if on_state:
                                    selected_widget.field_value = on_state
                                elif button_states:
                                    # Button states structure: {'normal': ['OnState'], 'down': ['Off', 'OnState']}
                                    found_on_value = False
                                    if isinstance(button_states, dict):
                                        # Try 'normal' key first (usually contains the on_state)
                                        if 'normal' in button_states and isinstance(button_states['normal'], list):
                                            for val in button_states['normal']:
                                                if val != "Off":
                                                    selected_widget.field_value = val
                                                    found_on_value = True
                                                    break
                                        
                                        # If not found, try other keys
                                        if not found_on_value:
                                            for state_key, state_values in button_states.items():
                                                if isinstance(state_values, list) and state_key != "Off":
                                                    for val in state_values:
                                                        if val != "Off":
                                                            selected_widget.field_value = val
                                                            found_on_value = True
                                                            break
                                                    if found_on_value:
                                                        break
                                    if not found_on_value:
                                        selected_widget.field_value = True
                                else:
                                    selected_widget.field_value = True
                                
                                selected_widget.update()
                                matched = True
                                print(f"✅ Selected widget[{target_index}] - Field: {field_name}, On State: {on_state}, Page: {page_num + 1}")
                        except Exception as e:
                            print(f"❌ Error setting selected widget[{target_index}] value: {str(e)}")
                            import traceback
                            traceback.print_exc()
                    else:
                        print(f"⚠️ Invalid radio index {target_index} for field {field_name} (has {len(radio_widgets)} options, valid range: 0-{len(radio_widgets)-1})")
                except ValueError:
                    # If not a number, try matching by on_state value (backward compatibility)
                    print(f"📝 Trying on_state matching for field {field_name} with value: {target_value}")
                    
                    # First, set all radio buttons to "Off"
                    for widget_info in radio_widgets:
                        page_num = widget_info['page']
                        widget_idx = widget_info['widget_idx']
                        
                        try:
                            page = doc[page_num]
                            widget_list = list(page.widgets())
                            if widget_idx < len(widget_list):
                                widget = widget_list[widget_idx]
                                
                                button_states = widget_info.get('button_states')
                                off_value = "Off"  # Default off value
                                
                                # button_states structure: {'normal': ['OnState'], 'down': ['Off', 'OnState']}
                                if button_states and isinstance(button_states, dict):
                                    # Check 'down' key first (usually has Off)
                                    if 'down' in button_states and isinstance(button_states['down'], list):
                                        if "Off" in button_states['down']:
                                            off_value = "Off"
                                    else:
                                        # Fallback: check all keys for "Off"
                                        for state_values in button_states.values():
                                            if isinstance(state_values, list) and "Off" in state_values:
                                                off_value = "Off"
                                                break
                                
                                widget.field_value = off_value
                                widget.update()
                        except Exception as e:
                            print(f"⚠️ Warning setting widget to Off: {str(e)}")
                            try:
                                page = doc[widget_info['page']]
                                widget_list = list(page.widgets())
                                if widget_info['widget_idx'] < len(widget_list):
                                    widget = widget_list[widget_info['widget_idx']]
                                    widget.field_value = False
                                    widget.update()
                            except:
                                pass
                    
                    # Now find and select the matching widget
                    for widget_info in radio_widgets:
                        page_num = widget_info['page']
                        widget_idx = widget_info['widget_idx']
                        on_state = widget_info.get('on_state')
                        
                        try:
                            page = doc[page_num]
                            widget_list = list(page.widgets())
                            if widget_idx < len(widget_list):
                                widget = widget_list[widget_idx]
                                
                                print(f"   Checking: On State: {on_state}, Target: {target_value}, Page: {page_num + 1}")
                                
                                # If frontend value matches PDF on_state, select this radio
                                if on_state is not None and str(on_state) == target_value:
                                    widget.field_value = on_state
                                    widget.update()
                                    matched = True
                                    print(f"✅ Set widget to True - On State {on_state} matches target {target_value}")
                        except Exception as e:
                            print(f"❌ Error getting on_state for widget: {str(e)}")
                
                print(f"   Result: {'✅ Matched' if matched else '⚠️ No match found'}\n")
                return matched or found_any_field
            
            return found_any_field
        except Exception as e:
            print(f"Error filling field directly {field_name}: {str(e)}")
            import traceback
            traceback.print_exc()
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
    
    def _print_radio_fields(self, doc: Any) -> None:
        """
        Print all radio button fields found in the PDF with their details
        Based on MuPDF.NET Widget documentation: https://mupdfnet.readthedocs.io/en/latest/classes/Widget.html
        
        Args:
            doc: PyMuPDF document
        """
        try:
            print("\n" + "="*80)
            print("RADIO BUTTON FIELDS DETECTION")
            print("="*80)
            
            radio_fields = {}
            total_radio_widgets = 0
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                page_radios = []
                
                for widget in page.widgets():
                    field_type = widget.field_type
                    
                    # field_type 5 = PDF_WIDGET_TYPE_RADIOBUTTON
                    if field_type == 5:
                        total_radio_widgets += 1
                        field_name = widget.field_name
                        current_value = widget.field_value
                        
                        # Get button states (On/Off values)
                        try:
                            button_states = widget.button_states()
                        except:
                            button_states = None
                        
                        # Get OnState (the value that selects this radio)
                        try:
                            on_state = widget.on_state()
                        except:
                            on_state = None
                        
                        # Get field rect position
                        rect = widget.rect
                        
                        radio_info = {
                            "field_name": field_name,
                            "current_value": current_value,
                            "on_state": on_state,
                            "button_states": button_states,
                            "position": {
                                "x": round(rect.x0, 2),
                                "y": round(rect.y0, 2),
                                "width": round(rect.width, 2),
                                "height": round(rect.height, 2)
                            },
                            "page": page_num + 1
                        }
                        
                        page_radios.append(radio_info)
                        
                        # Group by field_name (radio buttons in same group share field_name)
                        if field_name not in radio_fields:
                            radio_fields[field_name] = []
                        radio_fields[field_name].append(radio_info)
                
                if page_radios:
                    print(f"\n📄 Page {page_num + 1}: Found {len(page_radios)} radio button widget(s)")
            
            # Print grouped radio fields
            if radio_fields:
                print(f"\n📊 Total Radio Button Groups: {len(radio_fields)}")
                print(f"📊 Total Radio Button Widgets: {total_radio_widgets}")
                print("\n" + "-"*80)
                
                for group_name, widgets in radio_fields.items():
                    print(f"\n🔘 Radio Group: '{group_name}'")
                    print(f"   Widgets in group: {len(widgets)}")
                    
                    for idx, widget in enumerate(widgets, 1):
                        print(f"\n   Widget #{idx}:")
                        print(f"      Current Value: {widget['current_value']}")
                        print(f"      On State: {widget['on_state']}")
                        print(f"      Button States: {widget['button_states']}")
                        print(f"      Position: x={widget['position']['x']}, y={widget['position']['y']}, "
                              f"w={widget['position']['width']}, h={widget['position']['height']}")
                        print(f"      Page: {widget['page']}")
            else:
                print("\n⚠️  No radio button fields found in this PDF")
            
            print("\n" + "="*80 + "\n")
            
        except Exception as e:
            print(f"⚠️  Error printing radio fields: {str(e)}")
            import traceback
            traceback.print_exc()
    
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