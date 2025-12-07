from .base import AgentResult, LLMClient
from kql_rules import analyze_kql, optimize_query

class OptimizerAgent:
    def __init__(self, use_google: bool = False):
        self.llm = LLMClient(use_google)

    def run(self, context: dict) -> AgentResult:
        q = context.get("fixed_query", context.get("query", ""))
        task = context.get("task")
        schema = context.get("schema") or {}
        evaluation = context.get("evaluation")  # Get evaluation result
        fulfills_task = evaluation.fulfills_task if evaluation else None
        optimized, changes = optimize_query(
            q,
            task,
            relevant_columns=schema.get("relevant_columns"),
            suggested_table=schema.get("suggested_table"),
        )
        a = analyze_kql(optimized)
        suggestions = (a.get("optimizations", []) or []) + changes
        task_alignment = None
        if self.llm.use_google:
            eval_status = "fulfills" if fulfills_task else "does NOT fulfill"
            eval_reason = evaluation.reason if evaluation and evaluation.reason else "Not evaluated"
            prompt = (
                "You are a KQL optimizer. Optimize the query while maintaining task fulfillment.\n\n"
                "TASK:\n" + str(task) + "\n\n"
                "QUERY TO OPTIMIZE:\n" + q + "\n\n"
                f"TASK EVALUATION: The query {eval_status} the task.\n"
                f"Evaluation details: {eval_reason}\n\n"
                "1. Suggest KQL performance improvements.\n"
                "2. Ensure optimizations maintain or improve alignment with the TASK requirements.\n"
                "3. If the query does NOT fulfill the task, prioritize optimizations that help achieve task requirements.\n"
                "4. Explain how the optimized query better serves the TASK.\n\n"
                "Return a JSON object with fields: 'optimized_query' (KQL query), 'improvements' (list of changes), 'task_alignment' (how optimization helps task)."
            )
            txt = self.llm.generate(prompt) or ""
            if txt:
                try:
                    import json
                    import re
                    json_match = re.search(r'\{.*?"optimized_query".*?"improvements".*?"task_alignment".*?\}', txt, re.DOTALL)
                    if json_match:
                        obj = json.loads(json_match.group(0))
                        opt_query = obj.get("optimized_query", "")
                        if opt_query:
                            optimized = opt_query
                        improvements = obj.get("improvements", [])
                        if improvements:
                            suggestions.extend(improvements if isinstance(improvements, list) else [improvements])
                        task_alignment = obj.get("task_alignment", "")
                except Exception:
                    # Fallback to simple query extraction
                    if txt and "|" in txt:
                        optimized = txt.strip()
        
        content = "Before vs After applied"
        if task_alignment:
            content += f"\n\n**Task Alignment:** {task_alignment}"
        return AgentResult(title="Optimizer", query=optimized, suggestions=suggestions, content=content)
