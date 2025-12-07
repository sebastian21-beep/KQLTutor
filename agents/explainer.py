from .base import AgentResult, LLMClient
from kql_rules import explain_natural

class ExplainerAgent:
    def __init__(self, use_google: bool = False):
        self.llm = LLMClient(use_google)

    def run(self, context: dict) -> AgentResult:
        q = context.get("optimized_query", context.get("query", ""))
        task = context.get("task", "")
        evaluation = context.get("evaluation")  # Get evaluation result
        fulfills_task = evaluation.fulfills_task if evaluation else None
        text, classification = explain_natural(q)
        task_connection = None
        if self.llm.use_google:
            eval_status = "fulfills" if fulfills_task else "does NOT fulfill"
            eval_reason = evaluation.reason if evaluation and evaluation.reason else "Not evaluated"
            prompt = (
                "You are a KQL explainer. Explain the query in context of the TASK evaluation.\n\n"
                "TASK:\n" + str(task) + "\n\n"
                "QUERY TO EXPLAIN:\n" + q + "\n\n"
                f"TASK EVALUATION: The query {eval_status} the task.\n"
                f"Evaluation details: {eval_reason}\n\n"
                "1. Explain what the KQL query returns and each pipe stage (3-4 sentences).\n"
                "2. Connect the explanation to how it relates to the TASK requirements.\n"
                "3. If the query does NOT fulfill the task, explain what's missing and what the query actually returns.\n"
                "4. Describe what insights this query provides for the TASK.\n\n"
                "Return a JSON object with fields: 'explanation' (detailed explanation), 'task_connection' (how query serves the task)."
            )
            txt = self.llm.generate(prompt) or ""
            if txt:
                try:
                    import json
                    import re
                    json_match = re.search(r'\{.*?"explanation".*?"task_connection".*?\}', txt, re.DOTALL)
                    if json_match:
                        obj = json.loads(json_match.group(0))
                        explanation = obj.get("explanation", "")
                        if explanation:
                            text = explanation
                        task_connection = obj.get("task_connection", "")
                except Exception:
                    # Fallback to simple text extraction
                    if txt:
                        text = txt
        
        schema = context.get("schema") or {}
        if schema and classification:
            classification = classification + " Using table: " + str(schema.get("suggested_table"))
        
        if task_connection:
            text += f"\n\n**Connection to Task:** {task_connection}"
        
        return AgentResult(title="Explainer", content=text, hints=[classification] if classification else None)
