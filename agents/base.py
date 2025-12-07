import os
from dataclasses import dataclass

@dataclass
class AgentResult:
    title: str
    content: str | None = None
    query: str | None = None
    hints: list[str] | None = None
    suggestions: list[str] | None = None
    fulfills_task: bool | None = None
    reason: str | None = None

class LLMClient:
    def __init__(self, use_google: bool = False):
        api_key = os.getenv("GOOGLE_API_KEY")
        self.use_google = use_google and bool(api_key)
        self.model = None
        self._last_error = None
        if self.use_google:
            try:
                import google.generativeai as genai
                if api_key:
                    genai.configure(api_key=api_key)
                    # Try to find an available model by listing them
                    model_name = None
                    available_model_names = []
                    
                    # List available models
                    try:
                        models = genai.list_models()
                        model_map = {}  # Map short names to full names
                        for model in models:
                            if hasattr(model, 'supported_generation_methods') and 'generateContent' in model.supported_generation_methods:
                                full_name = model.name  # Keep full name like 'models/gemini-1.5-flash'
                                # Extract short name for matching
                                short_name = full_name.split('/')[-1] if '/' in full_name else full_name
                                model_map[short_name] = full_name
                                available_model_names.append(short_name)
                        
                        # Prefer stable models for free tier (avoid experimental models that may have quota issues)
                        preferred_models = ['gemini-2.5-flash', 'gemini-2.5-pro', 'gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-pro', 'gemini-flash-latest']
                        for preferred in preferred_models:
                            if preferred in model_map:
                                model_name = model_map[preferred]  # Use full name
                                break
                        
                        # If no preferred model found, use first available
                        if not model_name and available_model_names:
                            first_short = available_model_names[0]
                            model_name = model_map.get(first_short, first_short)
                            
                    except Exception as list_error:
                        # If listing fails, try common free tier models directly
                        self._last_error = f"List models error: {str(list_error)}. Trying direct model names..."
                        preferred_models = ['gemini-2.5-flash', 'gemini-2.5-pro', 'gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-pro']
                        for preferred in preferred_models:
                            try:
                                # Test if model works by trying to create it
                                test_model = genai.GenerativeModel(preferred)
                                model_name = preferred
                                break
                            except Exception:
                                continue
                    
                    # If still no model found, try with 'models/' prefix
                    if not model_name:
                        try:
                            self.model = genai.GenerativeModel('models/gemini-2.5-flash')
                            model_name = 'models/gemini-2.5-flash'
                        except Exception:
                            pass
                    
                    if model_name:
                        self.model = genai.GenerativeModel(model_name)
                        self._model_name = model_name  # Store for debugging
                    else:
                        raise Exception(f"No available models found. Tried: {available_model_names if available_model_names else 'none'}")
                else:
                    self.use_google = False
            except Exception as e:
                # If initialization fails, disable Google AI
                self.use_google = False
                self.model = None
                self._last_error = str(e)

    def generate(self, prompt: str) -> str | None:
        if not self.use_google or not self.model:
            return None
        try:
            # Use the standard google.generativeai API
            response = self.model.generate_content(prompt)
            
            # Extract text from response
            if response is None:
                return None
            
            # Standard google.generativeai response format
            # The response object has a .text property that returns the generated text
            try:
                # Try accessing .text directly (it's a property, not a method)
                text = response.text
                if text and isinstance(text, str) and text.strip():
                    return text.strip()
            except AttributeError:
                # .text might not exist, try alternative access
                pass
            except Exception as e:
                # Some other error accessing .text
                pass
            
            # Alternative: get from candidates structure
            try:
                if hasattr(response, 'candidates') and response.candidates and len(response.candidates) > 0:
                    candidate = response.candidates[0]
                    if hasattr(candidate, 'content'):
                        content = candidate.content
                        if hasattr(content, 'parts') and content.parts and len(content.parts) > 0:
                            part = content.parts[0]
                            # Part can be a string or have a text attribute
                            if isinstance(part, str):
                                return part.strip()
                            elif hasattr(part, 'text'):
                                text = part.text
                                if text and isinstance(text, str):
                                    return text.strip()
            except Exception:
                pass
            
            # Last resort: try to convert response to string
            try:
                response_str = str(response)
                if response_str and response_str != "None":
                    return response_str
            except Exception:
                pass
            
            return None
        except Exception as e:
            # Store error for debugging (could be logged in production)
            error_msg = str(e)
            self._last_error = error_msg
            
            # Check if it's a quota error
            if '429' in error_msg or 'quota' in error_msg.lower() or 'rate limit' in error_msg.lower():
                # Quota exceeded - user needs to wait or check their plan
                self._last_error = f"Quota exceeded. Please wait and try again, or check your API plan. Error: {error_msg[:200]}"
            
            return None
