from .base import AgentResult, LLMClient
from kql_rules import explain_natural

class ExplainerAgent:
    def __init__(self, use_google: bool = False):
        self.llm = LLMClient(use_google)

    def run(self, context: dict) -> AgentResult:
        q = context.get("optimized_query", context.get("query", ""))
        text, classification = explain_natural(q)
        if self.llm.use_google:
            g = self.llm.generate("Explain KQL result and each pipe stage in 3-4 sentences: " + q)
            if g:
                text = g
        schema = context.get("schema") or {}
        if schema and classification:
            classification = classification + " Using table: " + str(schema.get("suggested_table"))
        return AgentResult(title="Explainer", content=text, hints=[classification] if classification else None)
