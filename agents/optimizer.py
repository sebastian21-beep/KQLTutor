from .base import AgentResult, LLMClient
from kql_rules import analyze_kql

class OptimizerAgent:
    def __init__(self, use_google: bool = False):
        self.llm = LLMClient(use_google)

    def run(self, context: dict) -> AgentResult:
        q = context.get("fixed_query", context.get("query", ""))
        a = analyze_kql(q)
        suggestions = a.get("optimizations", [])
        optimized = q
        if suggestions:
            optimized = q
        if self.llm.use_google:
            p = "Suggest KQL performance improvements and output optimized query only. Query:" + q
            g = self.llm.generate(p)
            if g:
                optimized = g
        return AgentResult(title="Optimizer", query=optimized, suggestions=suggestions)

