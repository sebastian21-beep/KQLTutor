from .base import AgentResult, LLMClient
from kql_rules import analyze_kql

class TutorAgent:
    def __init__(self, use_google: bool = False):
        self.llm = LLMClient(use_google)

    def run(self, context: dict) -> AgentResult:
        q = context.get("query", "")
        analysis = analyze_kql(q)
        hints = analysis.get("hints", [])
        task = context.get("task") or ""
        schema = context.get("schema") or {}
        evaluation = context.get("evaluation")  # Get evaluation result
        fulfills_task = evaluation.fulfills_task if evaluation else None
        lesson = [
            "Pick the correct table (e.g., SecurityEvent or SigninLogs)",
            "Add a time window with TimeGenerated >= ago(...)",
            "Use pipes to chain operators: where → project → summarize/distinct",
        ]
        alternatives = [
            "Try SigninLogs vs SecurityEvent depending on logon source",
            "For aggregation, use summarize count() by Field or dcount(Field)",
        ]
        if schema:
            stbl = schema.get("suggested_table")
            rcols = schema.get("relevant_columns") or []
            lesson.append(f"Suggested table: {stbl}; focus on columns: {', '.join(rcols)}")
        extra = None
        task_relevance = None
        if self.llm.use_google:
            eval_status = "fulfills" if fulfills_task else "does NOT fulfill"
            eval_reason = evaluation.reason if evaluation and evaluation.reason else "Not evaluated"
            prompt = (
                "You are a KQL tutor. Provide guidance based on the task evaluation.\n\n"
                "TASK:\n" + str(task) + "\n\n"
                "USER QUERY:\n" + q + "\n\n"
                f"TASK EVALUATION: The query {eval_status} the task.\n"
                f"Evaluation details: {eval_reason}\n\n"
                "1. Give a short KQL lesson (3 bullets) specifically tailored to help complete this TASK.\n"
                "2. Provide 2 alternative approaches that would help achieve the TASK.\n"
                "3. If the query does NOT fulfill the task, focus your lesson on addressing the missing requirements.\n"
                "4. Explain how your lesson directly relates to the TASK requirements.\n\n"
                "Return a JSON object with fields: 'lesson' (3 bullet points), 'alternatives' (2 items), 'task_relevance' (how lesson helps with task)."
            )
            txt = self.llm.generate(prompt) or ""
            if txt:
                try:
                    import json
                    import re
                    # Extract JSON from response
                    json_match = re.search(r'\{.*?"lesson".*?"alternatives".*?"task_relevance".*?\}', txt, re.DOTALL)
                    if json_match:
                        obj = json.loads(json_match.group(0))
                        lesson_text = obj.get("lesson", "")
                        if lesson_text:
                            if isinstance(lesson_text, list):
                                lesson.extend(lesson_text)
                            else:
                                lesson.append(lesson_text)
                        alt = obj.get("alternatives", [])
                        if alt:
                            alternatives.extend(alt if isinstance(alt, list) else [alt])
                        task_relevance = obj.get("task_relevance", "")
                except Exception:
                    # Fallback to simple text extraction
                    if txt:
                        lesson.append(txt)
        
        content = "\n".join(["- " + l for l in lesson])
        if task_relevance:
            content += f"\n\n**Relevance to Task:** {task_relevance}"
        return AgentResult(title="Tutor", hints=hints, content=content, suggestions=alternatives)
