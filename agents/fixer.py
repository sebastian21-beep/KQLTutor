from .base import AgentResult, LLMClient
from kql_rules import fix_query

class FixerAgent:
    def __init__(self, use_google: bool = False):
        self.llm = LLMClient(use_google)

    def run(self, context: dict) -> AgentResult:
        q = context.get("query", "")
        fixed = fix_query(q)
        if not fixed and self.llm.use_google:
            p = "Fix KQL syntax and semantics. Input:" + q
            fixed = self.llm.generate(p)
        return AgentResult(title="Fixer", query=fixed or q)

