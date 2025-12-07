from .base import AgentResult, LLMClient
from kql_rules import analyze_kql

class TutorAgent:
    def __init__(self, use_google: bool = False):
        self.llm = LLMClient(use_google)

    def run(self, context: dict) -> AgentResult:
        q = context.get("query", "")
        analysis = analyze_kql(q)
        hints = analysis.get("hints", [])
        extra = None
        if self.llm.use_google:
            prompt = "Teach KQL concepts for this query and task. Query:" + q + " Task:" + str(context.get("task"))
            extra = self.llm.generate(prompt)
            if extra:
                hints.append(extra)
        return AgentResult(title="Tutor", hints=hints, content=None)

