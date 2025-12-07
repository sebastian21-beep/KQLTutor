from .base import AgentResult, LLMClient
from kql_rules import fix_query, compute_diffs, render_commented_query, assess_task
import json

class FixerAgent:
    def __init__(self, use_google: bool = False):
        self.llm = LLMClient(use_google)

    def run(self, context: dict) -> AgentResult:
        q = context.get("query", "")
        schema = context.get("schema") or {}
        evaluation = context.get("evaluation")  # Get evaluation result
        fulfills = evaluation.fulfills_task if evaluation else None
        reason = evaluation.reason if evaluation else None
        corrected = None
        diffs = []
        commented = None
        
        if self.llm.use_google:
            eval_status = "fulfills" if fulfills else "does NOT fulfill"
            eval_reason = reason or "Not evaluated"
            missing_elements = evaluation.suggestions if evaluation and evaluation.suggestions else []
            prompt = (
                "You are a KQL fixer. Fix the query based on the task evaluation.\n\n"
                "TASK:\n" + str(context.get("task")) + "\n\n"
                "USER QUERY:\n" + q + "\n\n"
                f"TASK EVALUATION: The query {eval_status} the task.\n"
                f"Evaluation details: {eval_reason}\n"
                + (f"Missing elements: {', '.join(missing_elements)}\n" if missing_elements else "") + "\n"
                "IMPORTANT: Pay special attention to EventID values. For failed logins/logons, EventID must be 4625. "
                "If the query has a different EventID (like 5625, 4624, etc.) and the task requires failed logins, correct it to 4625.\n\n"
                "1. Explain in 2–3 bullet points what the user query returns.\n"
                "2. Based on the evaluation, provide a corrected KQL query that fulfils ALL TASK requirements.\n"
                "3. Ensure EventID values match the task requirements (4625 for failed logons).\n"
                "4. If the query already fulfills the task, suggest minor improvements or optimizations.\n"
                "5. Explain how the corrected query addresses each TASK requirement.\n\n"
                "Return a JSON object with fields: corrected_query (KQL query), task_coverage (how corrected query covers task requirements), improvements (list of changes made)."
            )
            txt = self.llm.generate(prompt) or ""
            try:
                import re
                json_match = re.search(r'\{.*?"corrected_query".*?"task_coverage".*?\}', txt, re.DOTALL)
                if json_match:
                    obj = json.loads(json_match.group(0))
                else:
                    obj = json.loads(txt)
                corrected_llm = obj.get("corrected_query")
                task_coverage = obj.get("task_coverage", "")
                improvements = obj.get("improvements", [])
                
                corrected = corrected_llm if corrected_llm else q
                
                if task_coverage and reason:
                    reason = reason + "\n\n**Task Coverage:** " + task_coverage
                if improvements:
                    diffs.extend(improvements if isinstance(improvements, list) else [improvements])
            except Exception:
                # If LLM parsing fails, use base fix_query
                corrected = q
        # Use evaluation's corrected query if available, otherwise fix the query
        if not corrected:
            _, _, corrected, _ = assess_task(str(context.get("task") or ""), q, schema)
        # Apply fix_query with task context to ensure EventID and other fixes are applied
        fixed = fix_query(corrected or q, suggested_table=schema.get("suggested_table"), task=context.get("task"))
        if not diffs:
            diffs = compute_diffs(q, fixed)
        commented = render_commented_query(fixed, diffs)
        return AgentResult(title="Fixer", query=commented or fixed or q, suggestions=diffs, fulfills_task=fulfills, reason=reason)
