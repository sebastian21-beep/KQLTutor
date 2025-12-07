from .base import AgentResult, LLMClient

class ExplainerAgent:
    def __init__(self, use_google: bool = False):
        self.llm = LLMClient(use_google)

    def run(self, context: dict) -> AgentResult:
        q = context.get("optimized_query", context.get("query", ""))
        parts = [p.strip() for p in q.split("|") if p.strip()]
        desc = []
        for i, p in enumerate(parts):
            desc.append(str(i + 1) + ": " + p)
        text = "\n".join(desc)
        if self.llm.use_google:
            g = self.llm.generate("Explain KQL result and each pipe stage: " + q)
            if g:
                text = g
        return AgentResult(title="Explainer", content=text)

