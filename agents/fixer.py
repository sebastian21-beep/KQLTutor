from .base import AgentResult, LLMClient
from kql_rules import fix_query, compute_diffs, render_commented_query

class FixerAgent:
    def __init__(self, use_google: bool = False):
        self.llm = LLMClient(use_google)

    def run(self, context: dict) -> AgentResult:
        q = context.get("query", "")
        schema = context.get("schema") or {}
        fixed = fix_query(q, suggested_table=schema.get("suggested_table"))
        diffs = compute_diffs(q, fixed)
        commented = render_commented_query(fixed, diffs)
        if not fixed and self.llm.use_google:
            p = "Fix KQL syntax and semantics. Input:" + q
            fixed = self.llm.generate(p)
        return AgentResult(title="Fixer", query=commented or fixed or q, suggestions=diffs)
