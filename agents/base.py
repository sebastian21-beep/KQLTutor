import os
from dataclasses import dataclass

@dataclass
class AgentResult:
    title: str
    content: str | None = None
    query: str | None = None
    hints: list[str] | None = None
    suggestions: list[str] | None = None

class LLMClient:
    def __init__(self, use_google: bool = False):
        self.use_google = use_google and bool(os.getenv("GOOGLE_API_KEY"))
        self.model = None
        if self.use_google:
            try:
                import google.generativeai as genai
                genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
                self.model = genai.GenerativeModel("gemini-1.5-flash")
            except Exception:
                self.use_google = False

    def generate(self, prompt: str) -> str | None:
        if not self.use_google or not self.model:
            return None
        try:
            r = self.model.generate_content(prompt)
            return r.text
        except Exception:
            return None

