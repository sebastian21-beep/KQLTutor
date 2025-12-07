from .base import AgentResult, LLMClient
from kql_rules import analyze_kql, optimize_query

class OptimizerAgent:
    def __init__(self, use_google: bool = False):
        self.llm = LLMClient(use_google)

    def run(self, context: dict) -> AgentResult:
        q = context.get("fixed_query", context.get("query", ""))
        task = context.get("task")
        schema = context.get("schema") or {}
        optimized, changes = optimize_query(
            q,
            task,
            relevant_columns=schema.get("relevant_columns"),
            suggested_table=schema.get("suggested_table"),
        )
        a = analyze_kql(optimized)
        suggestions = (a.get("optimizations", []) or []) + changes
        if self.llm.use_google:
            p = "Suggest KQL performance improvements and output optimized query only. Query:" + q
            g = self.llm.generate(p)
            if g:
                optimized = g
        return AgentResult(title="Optimizer", query=optimized, suggestions=suggestions, content="Before vs After applied")
