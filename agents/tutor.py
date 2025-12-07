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
        if self.llm.use_google:
            prompt = (
                "Give a short KQL lesson (3 bullets) and 2 alternatives for this task. "
                + "Query:" + q + " Task:" + str(task)
            )
            extra = self.llm.generate(prompt)
            if extra:
                lesson.append(extra)
        content = "\n".join(["- " + l for l in lesson])
        return AgentResult(title="Tutor", hints=hints, content=content, suggestions=alternatives)
