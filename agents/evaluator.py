from .base import AgentResult, LLMClient
from kql_rules import assess_task
import json
import re

class EvaluatorAgent:
    def __init__(self, use_google: bool = False):
        self.llm = LLMClient(use_google)

    def run(self, context: dict) -> AgentResult:
        """
        Evaluates whether the query fulfills the task requirements.
        Returns an AgentResult with fulfills_task, reason, and evaluation details.
        """
        q = context.get("query", "")
        task = context.get("task", "")
        schema = context.get("schema") or {}
        
        # Always run base assessment first
        fulfills_base, mismatches_base, corrected_base, reason_base = assess_task(task, q, schema)
        
        # Initialize variables with base assessment values
        fulfills = fulfills_base
        reason = reason_base or "Evaluation completed"
        evaluation_details = None
        
        # Get detailed LLM evaluation if available
        if self.llm.use_google:
            prompt = (
                "You are a KQL task evaluator. Strictly evaluate if the query fulfills ALL task requirements.\n\n"
                "TASK:\n" + str(task) + "\n\n"
                "QUERY TO EVALUATE:\n" + q + "\n\n"
                "Evaluate the query against the TASK requirements:\n"
                "1. List ALL task requirements from the task description.\n"
                "2. Check if the query addresses EACH requirement.\n"
                "3. Identify ANY missing or incorrect elements.\n"
                "4. Determine: DOES THIS QUERY FULFILL THE TASK? (Answer 'No' if ANY requirement is missing. Only 'Yes' if ALL are met).\n"
                "5. Provide a detailed reason explaining your evaluation.\n\n"
                "Return a JSON object with fields: "
                "fulfills_task (Yes/No - be strict), "
                "task_requirements (list of requirements from task), "
                "query_coverage (what the query does), "
                "missing_elements (list of missing requirements), "
                "reason (detailed evaluation explanation)."
            )
            txt = self.llm.generate(prompt) or ""
            if txt:
                try:
                    json_match = re.search(r'\{.*?"fulfills_task".*?"reason".*?\}', txt, re.DOTALL)
                    if json_match:
                        obj = json.loads(json_match.group(0))
                    else:
                        obj = json.loads(txt)
                    
                    ft = obj.get("fulfills_task")
                    fulfills_llm = True if isinstance(ft, bool) and ft else (str(ft or "").lower() == "yes")
                    
                    # Use conservative approach: both must agree for Yes
                    fulfills = fulfills_base and fulfills_llm
                    
                    # Build comprehensive reason
                    reasons = []
                    if not fulfills_base and reason_base:
                        reasons.append(f"Validation: {reason_base}")
                    if not fulfills_llm:
                        llm_reason = obj.get("reason", "")
                        if llm_reason:
                            reasons.append(f"LLM Analysis: {llm_reason}")
                    
                    if reasons:
                        reason = " | ".join(reasons)
                    else:
                        reason = obj.get("reason") or reason_base or "Evaluation completed"
                    
                    # Collect evaluation details
                    evaluation_details = {
                        "task_requirements": obj.get("task_requirements", []),
                        "query_coverage": obj.get("query_coverage", ""),
                        "missing_elements": obj.get("missing_elements", []),
                    }
                    
                    # Add evaluation details to reason
                    if evaluation_details.get("task_requirements"):
                        reason += f"\n\n**Task Requirements:** {', '.join(evaluation_details['task_requirements']) if isinstance(evaluation_details['task_requirements'], list) else evaluation_details['task_requirements']}"
                    if evaluation_details.get("missing_elements"):
                        reason += f"\n\n**Missing Elements:** {', '.join(evaluation_details['missing_elements']) if isinstance(evaluation_details['missing_elements'], list) else evaluation_details['missing_elements']}"
                    
                except Exception:
                    # If LLM parsing fails, use base assessment
                    fulfills = fulfills_base
                    reason = reason_base or "Evaluation completed"
        else:
            # No LLM, use base assessment
            fulfills = fulfills_base
            reason = reason_base or "Evaluation completed"
        
        return AgentResult(
            title="Evaluator",
            content=reason,
            fulfills_task=fulfills,
            reason=reason,
            suggestions=evaluation_details.get("missing_elements", []) if evaluation_details else []
        )

