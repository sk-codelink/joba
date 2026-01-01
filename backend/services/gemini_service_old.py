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
            logger.warning("No GEMINI_API_KEY found. Using fallback rule-based approach.")
        elif not GEMINI_AVAILABLE:
            logger.warning("Google Generative AI package not installed. Using fallback rule-based approach.")
        else:
            try:
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel('gemini-2.5-pro')
                logger.info("Gemini 2.5 Pro initialized successfully")
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

            # Run in thread pool to avoid blocking
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
    
    def _rule_based_filling(self, prompt: str) -> str:
        try:
            lines = prompt.split('\n')
            user_input = ""
            form_fields = {}
            
            for i, line in enumerate(lines):
                if line.startswith("User Input:"):
                    if i + 1 < len(lines):
                        user_input = lines[i + 1].strip()
                    break
            
            in_fields_section = False
            for line in lines:
                if line.startswith("Available Form Fields"):
                    in_fields_section = True
                    continue
                if in_fields_section and line.startswith("- "):
                    field_info = line[2:].strip()
                    if " | " in field_info and "(" in field_info:
                        parts = field_info.split(" | ")
                        if len(parts) >= 2:
                            field_name = parts[0].strip()
                            remaining = " | ".join(parts[1:])
                            if "(" in remaining:
                                label_and_type = remaining.rsplit("(", 1)
                                label = label_and_type[0].strip()
                                field_type = label_and_type[1].rstrip(")").strip()
                                
                                form_fields[field_name] = {
                                    'label': label,
                                    'type': field_type,
                                    'combined': f"{field_name} | {label}"
                                }
            
            filled_fields = {}
            reasoning_parts = []
            
            if user_input:
                user_input_lower = user_input.lower()
                
                for field_name, field_data in form_fields.items():
                    field_name_lower = field_name.lower()
                    label = field_data.get('label', '')
                    label_lower = label.lower()
                    field_type = field_data.get('type', 'text')
                    
                    filled_value = None
                    
                    name_keywords = ['name', 'patient', 'first', 'last', 'full']
                    if any(kw in field_name_lower or kw in label_lower for kw in name_keywords):
                        if any(pattern in user_input_lower for pattern in ['name is', 'my name', 'called', 'i am', "i'm"]):
                            names = self._extract_names(user_input)
                            if names:
                                name_parts = names[0].split()
                                if ('first' in field_name_lower or 'first' in label_lower) and len(name_parts) > 0:
                                    filled_value = name_parts[0]
                                elif ('last' in field_name_lower or 'last' in label_lower) and len(name_parts) > 1:
                                    filled_value = name_parts[-1]
                                elif 'full' in field_name_lower or 'full' in label_lower or 'patient' in field_name_lower or 'patient' in label_lower:
                                    filled_value = names[0]
                                else:
                                    filled_value = names[0]
                                reasoning_parts.append(f"Matched name to {field_name} ({label})")
                    
                    elif any(kw in field_name_lower or kw in label_lower for kw in ['age']):
                        age = self._extract_age(user_input)
                        if age:
                            filled_value = age
                            reasoning_parts.append(f"Matched age to {field_name} ({label})")
                    
                    elif any(kw in field_name_lower or kw in label_lower for kw in ['birth', 'dob', 'born']):
                        dob = self._extract_date_of_birth(user_input)
                        if dob:
                            filled_value = dob
                            reasoning_parts.append(f"Matched date of birth to {field_name} ({label})")
                    
                    elif any(kw in field_name_lower or kw in label_lower for kw in ['gender', 'sex']):
                        gender = self._extract_gender(user_input)
                        if gender:
                            filled_value = gender
                            reasoning_parts.append(f"Matched gender to {field_name} ({label})")
                    
                    elif any(kw in field_name_lower or kw in label_lower for kw in ['address', 'street', 'home']) and not any(exclude in field_name_lower or exclude in label_lower for exclude in ['city', 'state', 'zip', 'postal']):
                        address = self._extract_address(user_input)
                        if address:
                            filled_value = address
                            reasoning_parts.append(f"Matched address to {field_name} ({label})")
                    
                    elif any(kw in field_name_lower or kw in label_lower for kw in ['city']):
                        city = self._extract_city(user_input)
                        if city:
                            filled_value = city
                            reasoning_parts.append(f"Matched city to {field_name} ({label})")
                    
                    elif any(kw in field_name_lower or kw in label_lower for kw in ['state']):
                        state = self._extract_state(user_input)
                        if state:
                            filled_value = state
                            reasoning_parts.append(f"Matched state to {field_name} ({label})")
                    
                    elif any(kw in field_name_lower or kw in label_lower for kw in ['zip', 'postal']):
                        zip_code = self._extract_zip(user_input)
                        if zip_code:
                            filled_value = zip_code
                            reasoning_parts.append(f"Matched ZIP code to {field_name} ({label})")
                    
                    elif any(kw in field_name_lower or kw in label_lower for kw in ['phone', 'telephone', 'mobile', 'contact']) and not any(exclude in field_name_lower or exclude in label_lower for exclude in ['emergency', 'doctor', 'physician']):
                        phone = self._extract_phone(user_input)
                        if phone:
                            filled_value = phone
                            reasoning_parts.append(f"Matched phone to {field_name} ({label})")
                    
                    elif any(kw in field_name_lower or kw in label_lower for kw in ['email', 'mail']):
                        email = self._extract_email(user_input)
                        if email:
                            filled_value = email
                            reasoning_parts.append(f"Matched email to {field_name} ({label})")
                    
                    elif any(kw in field_name_lower or kw in label_lower for kw in ['employer', 'company', 'work']):
                        employer = self._extract_employer(user_input)
                        if employer:
                            filled_value = employer
                            reasoning_parts.append(f"Matched employer to {field_name} ({label})")
                    
                    elif any(kw in field_name_lower or kw in label_lower for kw in ['occupation', 'job', 'title']):
                        occupation = self._extract_occupation(user_input)
                        if occupation:
                            filled_value = occupation
                            reasoning_parts.append(f"Matched occupation to {field_name} ({label})")
                    
                    elif any(kw in field_name_lower or kw in label_lower for kw in ['income', 'salary', 'earnings']):
                        income = self._extract_income(user_input)
                        if income:
                            filled_value = income
                            reasoning_parts.append(f"Matched income to {field_name} ({label})")
                    
                    # 13. Emergency contact matching
                    elif any(kw in field_name_lower or kw in label_lower for kw in ['emergency']):
                        if any(kw in field_name_lower or kw in label_lower for kw in ['phone', 'telephone', 'contact']):
                            emergency_phone = self._extract_emergency_phone(user_input)
                            if emergency_phone:
                                filled_value = emergency_phone
                                reasoning_parts.append(f"Matched emergency phone to {field_name} ({label})")
                        else:
                            emergency_contact = self._extract_emergency_contact(user_input)
                            if emergency_contact:
                                filled_value = emergency_contact
                                reasoning_parts.append(f"Matched emergency contact to {field_name} ({label})")
                    
                    # 14. Insurance matching
                    elif any(kw in field_name_lower or kw in label_lower for kw in ['insurance', 'policy', 'group']):
                        if any(kw in field_name_lower or kw in label_lower for kw in ['policy']):
                            policy = self._extract_policy_number(user_input)
                            if policy:
                                filled_value = policy
                                reasoning_parts.append(f"Matched policy number to {field_name} ({label})")
                        elif any(kw in field_name_lower or kw in label_lower for kw in ['group']):
                            group = self._extract_group_number(user_input)
                            if group:
                                filled_value = group
                                reasoning_parts.append(f"Matched group number to {field_name} ({label})")
                        else:
                            insurance = self._extract_insurance_company(user_input)
                            if insurance:
                                filled_value = insurance
                                reasoning_parts.append(f"Matched insurance company to {field_name} ({label})")
                    
                    # 15. Medical conditions (checkboxes)
                    elif field_type == 'checkbox':
                        conditions_map = {
                            'diabetes': ['diabetes', 'diabetic', 'insulin'],
                            'hypertension': ['hypertension', 'high blood pressure', 'blood pressure'],
                            'heart': ['heart disease', 'cardiac', 'heart'],
                            'cancer': ['cancer', 'tumor', 'oncology'],
                            'asthma': ['asthma', 'inhaler'],
                            'medication': ['medication', 'medicine', 'pills', 'drugs', 'take', 'taking']
                        }
                        
                        for condition_key, condition_terms in conditions_map.items():
                            if (condition_key in field_name_lower or condition_key in label_lower or 
                                any(term in label_lower for term in condition_terms)):
                                if any(term in user_input_lower for term in condition_terms):
                                    filled_value = True
                                    reasoning_parts.append(f"Checked {field_name} ({label}) based on medical condition")
                                    break
                    
                    # 16. Doctor/Medical provider matching
                    elif any(kw in field_name_lower or kw in label_lower for kw in ['doctor', 'physician', 'provider']):
                        if any(kw in field_name_lower or kw in label_lower for kw in ['phone', 'telephone']):
                            doctor_phone = self._extract_doctor_phone(user_input)
                            if doctor_phone:
                                filled_value = doctor_phone
                                reasoning_parts.append(f"Matched doctor phone to {field_name} ({label})")
                        else:
                            doctor = self._extract_doctor_name(user_input)
                            if doctor:
                                filled_value = doctor
                                reasoning_parts.append(f"Matched doctor name to {field_name} ({label})")
                    
                    # 17. Medical history matching
                    elif any(kw in field_name_lower or kw in label_lower for kw in ['surgery', 'operation']):
                        surgery = self._extract_surgery_history(user_input)
                        if surgery:
                            filled_value = surgery
                            reasoning_parts.append(f"Matched surgery history to {field_name} ({label})")
                    
                    elif any(kw in field_name_lower or kw in label_lower for kw in ['hospital', 'admission']):
                        hospitalization = self._extract_hospitalization_history(user_input)
                        if hospitalization:
                            filled_value = hospitalization
                            reasoning_parts.append(f"Matched hospitalization to {field_name} ({label})")
                    
                    elif any(kw in field_name_lower or kw in label_lower for kw in ['allerg']):
                        allergies = self._extract_allergies(user_input)
                        if allergies:
                            filled_value = allergies
                            reasoning_parts.append(f"Matched allergies to {field_name} ({label})")
                    
                    elif any(kw in field_name_lower or kw in label_lower for kw in ['medication']) and field_type != 'checkbox':
                        if any(kw in field_name_lower or kw in label_lower for kw in ['current']):
                            medications = self._extract_current_medications(user_input)
                            if medications:
                                filled_value = medications
                                reasoning_parts.append(f"Matched current medications to {field_name} ({label})")
                    
                    if filled_value is not None:
                        filled_fields[field_name] = filled_value
            
            # Create response
            response = {
                **filled_fields,
                "reasoning": f"Rule-based analysis completed. {'; '.join(reasoning_parts) if reasoning_parts else 'No clear matches found for automatic filling.'}"
            }
            
            return json.dumps(response)
            
        except Exception as e:
            logger.error(f"Rule-based filling error: {e}")
            return json.dumps({
                "reasoning": "Error in automatic form filling. Please fill the fields manually."
            })
    
    def _extract_names(self, text: str) -> list:
        """Extract names from text"""
        import re
        patterns = [
            r"name is ([A-Z][a-z]+ [A-Z][a-z]+)",
            r"my name [is]* ([A-Z][a-z]+ [A-Z][a-z]+)",
            r"called ([A-Z][a-z]+ [A-Z][a-z]+)",
            r"I'm ([A-Z][a-z]+ [A-Z][a-z]+)"
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                return matches
        return []
    
    def _extract_age(self, text: str) -> Optional[str]:
        """Extract age from text"""
        import re
        patterns = [
            r"(\d+) years old",
            r"age (\d+)",
            r"I'm (\d+)",
            r"(\d+) year old"
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                return matches[0]
        return None
    
    def _extract_address(self, text: str) -> Optional[str]:
        """Extract address from text"""
        import re
        patterns = [
            r"live at ([^,]+(?:,[^,]+)*)",
            r"address (?:is )?([^,]+(?:,[^,]+)*)",
            r"(\d+[^,]+(?:Street|St|Avenue|Ave|Road|Rd|Lane|Ln|Drive|Dr|Boulevard|Blvd)[^,]*(?:,[^,]+)*)"
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                return matches[0].strip()
        return None
    
    def _extract_phone(self, text: str) -> Optional[str]:
        """Extract phone number from text"""
        import re
        patterns = [
            r"(\d{3}-\d{3}-\d{4})",
            r"\((\d{3})\) (\d{3})-(\d{4})",
            r"(\d{10})"
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text)
            if matches:
                if isinstance(matches[0], tuple):
                    return "".join(matches[0])
                return matches[0]
        return None
    
    def _extract_email(self, text: str) -> Optional[str]:
        """Extract email from text"""
        import re
        pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
        matches = re.findall(pattern, text)
        return matches[0] if matches else None

    def _extract_date_of_birth(self, text: str) -> Optional[str]:
        """Extract date of birth from text"""
        import re
        patterns = [
            r"born on ([A-Za-z]+ \d+, \d{4})",
            r"birth.*?(\d{1,2}/\d{1,2}/\d{4})",
            r"birth.*?(\d{1,2}-\d{1,2}-\d{4})",
            r"(\d{1,2}/\d{1,2}/\d{4})",
            r"([A-Za-z]+ \d+, \d{4})"
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                return matches[0]
        return None

    def _extract_gender(self, text: str) -> Optional[str]:
        """Extract gender from text"""
        text_lower = text.lower()
        if 'female' in text_lower or 'woman' in text_lower:
            return 'Female'
        elif 'male' in text_lower and 'female' not in text_lower:
            return 'Male'
        return None

    def _extract_city(self, text: str) -> Optional[str]:
        """Extract city from address"""
        import re
        # Look for city in address patterns
        patterns = [
            r"live at [^,]+,\s*([^,]+),\s*[A-Z]{2}",
            r"address.*?[^,]+,\s*([^,]+),\s*[A-Z]{2}",
            r",\s*([^,]+),\s*[A-Z]{2}\s*\d{5}"
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                return matches[0].strip()
        return None

    def _extract_state(self, text: str) -> Optional[str]:
        """Extract state from address"""
        import re
        patterns = [
            r",\s*([A-Z]{2})\s*\d{5}",
            r"live at.*?,.*?,\s*([A-Z]{2})",
            r"address.*?,.*?,\s*([A-Z]{2})"
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text)
            if matches:
                return matches[0]
        return None

    def _extract_zip(self, text: str) -> Optional[str]:
        """Extract ZIP code from address"""
        import re
        pattern = r"\b(\d{5}(-\d{4})?)\b"
        matches = re.findall(pattern, text)
        return matches[0][0] if matches else None

    def _extract_employer(self, text: str) -> Optional[str]:
        """Extract employer/company name"""
        import re
        patterns = [
            r"work(?:ing)? at ([^,.\n]+)",
            r"employed (?:at|by) ([^,.\n]+)",
            r"company.*?([A-Z][^,.\n]+(?:Corporation|Corp|Inc|LLC|Company))",
            r"([A-Z][^,.\n]*(?:Corporation|Corp|Inc|LLC|Company))"
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                return matches[0].strip()
        return None

    def _extract_occupation(self, text: str) -> Optional[str]:
        """Extract occupation/job title"""
        import re
        patterns = [
            r"(?:i am|i'm) (?:a |an )?([^,.\n]*engineer[^,.\n]*)",
            r"(?:i am|i'm) (?:a |an )?([^,.\n]*doctor[^,.\n]*)",
            r"(?:i am|i'm) (?:a |an )?([^,.\n]*nurse[^,.\n]*)",
            r"(?:i am|i'm) (?:a |an )?([^,.\n]*teacher[^,.\n]*)",
            r"(?:i am|i'm) (?:a |an )?([^,.\n]*manager[^,.\n]*)",
            r"(?:i work as|job.*?is) (?:a |an )?([^,.\n]+)",
            r"(?:occupation|profession).*?([^,.\n]+)"
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                return matches[0].strip()
        return None

    def _extract_income(self, text: str) -> Optional[str]:
        """Extract annual income"""
        import re
        patterns = [
            r"income.*?\$?([\d,]+)",
            r"salary.*?\$?([\d,]+)",
            r"earn.*?\$?([\d,]+)",
            r"\$?([\d,]+).*?(?:annual|year|yearly)"
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                amount = matches[0].replace(',', '')
                if amount.isdigit():
                    return f"${int(amount):,}"
        return None

    def _extract_emergency_contact(self, text: str) -> Optional[str]:
        """Extract emergency contact name"""
        import re
        patterns = [
            r"emergency.*?contact.*?([A-Z][a-z]+ [A-Z][a-z]+)",
            r"contact.*?([A-Z][a-z]+ [A-Z][a-z]+).*?(\d{3}[-.]?\d{3}[-.]?\d{4})"
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                if isinstance(matches[0], tuple):
                    return matches[0][0]
                return matches[0]
        return None

    def _extract_emergency_phone(self, text: str) -> Optional[str]:
        """Extract emergency contact phone"""
        import re
        emergency_section = ""
        lines = text.split('.')
        for line in lines:
            if 'emergency' in line.lower():
                emergency_section = line
                break
        
        if emergency_section:
            phone = self._extract_phone(emergency_section)
            if phone:
                return phone
        return None

    def _extract_insurance_company(self, text: str) -> Optional[str]:
        """Extract insurance company name"""
        import re
        patterns = [
            r"insurance.*?through ([^,.\n]+)",
            r"insurance.*?([A-Z][^,.\n]*(?:Insurance|Health|Medical|Care|Cross|Shield))",
            r"([A-Z][^,.\n]*(?:Blue Cross|Aetna|Cigna|Humana|UnitedHealth))"
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                return matches[0].strip()
        return None

    def _extract_policy_number(self, text: str) -> Optional[str]:
        """Extract insurance policy number"""
        import re
        patterns = [
            r"policy.*?number.*?([A-Z0-9]+)",
            r"policy.*?([A-Z]{2}\d+)"
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                return matches[0]
        return None

    def _extract_group_number(self, text: str) -> Optional[str]:
        """Extract insurance group number"""
        import re
        patterns = [
            r"group.*?number.*?([A-Z0-9]+)",
            r"group.*?([A-Z]{3}\d+)"
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                return matches[0]
        return None

    def _extract_doctor_name(self, text: str) -> Optional[str]:
        """Extract doctor/physician name"""
        import re
        patterns = [
            r"(?:doctor|physician|dr\.?).*?([A-Z][a-z]+ [A-Z][a-z]+)",
            r"primary care.*?([A-Z][a-z]+ [A-Z][a-z]+)",
            r"Dr\.?\s+([A-Z][a-z]+ [A-Z][a-z]+)"
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                return f"Dr. {matches[0]}"
        return None

    def _extract_doctor_phone(self, text: str) -> Optional[str]:
        """Extract doctor's phone number"""
        import re
        doctor_section = ""
        lines = text.split('.')
        for line in lines:
            if any(word in line.lower() for word in ['doctor', 'physician', 'dr']):
                doctor_section = line
                # Also check the next line for phone
                idx = text.find(line)
                remaining = text[idx + len(line):]
                next_sentence = remaining.split('.')[0] if '.' in remaining else remaining
                doctor_section += next_sentence
                break
        
        if doctor_section:
            phone = self._extract_phone(doctor_section)
            if phone:
                return phone
        return None

    def _extract_surgery_history(self, text: str) -> Optional[str]:
        """Extract surgery history"""
        import re
        patterns = [
            r"(had.*?(?:surgery|operation|removed).*?\d{4})",
            r"(appendix.*?removed.*?\d{4})",
            r"(surgery.*?\d{4})"
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                return matches[0].strip()
        return None

    def _extract_hospitalization_history(self, text: str) -> Optional[str]:
        """Extract hospitalization history"""
        import re
        patterns = [
            r"(hospitalized.*?\d{4})",
            r"(hospital.*?\d{4})",
            r"(admitted.*?\d{4})"
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                return matches[0].strip()
        return None

    def _extract_allergies(self, text: str) -> Optional[str]:
        """Extract allergies"""
        import re
        patterns = [
            r"allergic to ([^.\n]+)",
            r"allerg(?:y|ies).*?([^.\n]+)"
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                return matches[0].strip()
        return None

    def _extract_current_medications(self, text: str) -> Optional[str]:
        """Extract current medications"""
        import re
        patterns = [
            r"(?:take|taking).*?(?:medication|medicine)s?.*?:?\s*([^.\n]+)",
            r"current.*?medication.*?:?\s*([^.\n]+)",
            r"medications?.*?:?\s*([^.\n]+mg[^.\n]*)"
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                return matches[0].strip()
        return None
