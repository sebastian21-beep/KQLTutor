from .base import AgentResult, LLMClient
import random
import json

class CreatorAgent:
    def __init__(self, use_google: bool = False):
        self.llm = LLMClient(use_google)

    def run(self, context: dict) -> AgentResult:
        level = context.get("level", "Easy")

        def _fallback(level: str) -> AgentResult:
            if level == "Easy":
                choices = [
                    (
                        "Top 5 users by event count today\n"
                        "• Table: SecurityEvent\n"
                        "• Time range: From start of today (startofday(now()))\n"
                        "• Group by: Account\n"
                        "• Aggregation: Count events per user\n"
                        "• Sort: Top 5 by count descending",
                        "SecurityEvent | where TimeGenerated >= startofday(now()) | summarize EventCount = count() by Account | top 5 by EventCount desc",
                    ),
                    (
                        "Distinct hosts with failed logins in 24h\n"
                        "• Table: SecurityEvent\n"
                        "• Time range: Last 24 hours (ago(24h))\n"
                        "• Filter: EventID == 4625 (failed logon)\n"
                        "• Output: Distinct HostName values",
                        "SecurityEvent | where TimeGenerated >= ago(24h) and EventID == 4625 | distinct HostName",
                    ),
                    (
                        "Count sign-ins per user today\n"
                        "• Table: SigninLogs\n"
                        "• Time range: From start of today (startofday(now()))\n"
                        "• Group by: UserPrincipalName\n"
                        "• Aggregation: Count sign-ins per user\n"
                        "• Sort: By count descending",
                        "SigninLogs | where TimeGenerated >= startofday(now()) | summarize Count = count() by UserPrincipalName | order by Count desc",
                    ),
                ]
            else:
                choices = [
                    (
                        "Failed logons per host in 7d with distinct user count\n"
                        "• Table: SecurityEvent\n"
                        "• Time range: Last 7 days (ago(7d))\n"
                        "• Filter: EventID == 4625 (failed logon)\n"
                        "• Group by: HostName\n"
                        "• Aggregation: Distinct count of Account (dcount)\n"
                        "• Sort: By distinct user count descending",
                        "SecurityEvent | where TimeGenerated >= ago(7d) and EventID == 4625 | summarize Users=dcount(Account) by HostName | order by Users desc",
                    ),
                    (
                        "Hourly sign-in trends by result type\n"
                        "• Table: SigninLogs\n"
                        "• Time range: Last 24 hours (ago(24h))\n"
                        "• Group by: TimeGenerated (1-hour bins) and ResultType\n"
                        "• Aggregation: Count per hour and result type\n"
                        "• Sort: By TimeGenerated ascending",
                        "SigninLogs | where TimeGenerated >= ago(24h) | summarize count() by bin(TimeGenerated, 1h), ResultType | order by TimeGenerated asc",
                    ),
                    (
                        "Failed sign-ins by user with IP visibility\n"
                        "• Table: SigninLogs\n"
                        "• Time range: Last 7 days (ago(7d))\n"
                        "• Filter: ResultType != '0' (failed sign-ins)\n"
                        "• Columns: UserPrincipalName, IPAddress, TimeGenerated\n"
                        "• Group by: UserPrincipalName\n"
                        "• Aggregation: Count failures per user\n"
                        "• Sort: By failure count descending",
                        "SigninLogs | where TimeGenerated >= ago(7d) and ResultType != '0' | project UserPrincipalName, IPAddress, TimeGenerated | summarize Failures=count() by UserPrincipalName | order by Failures desc",
                    ),
                ]
            t, q = random.choice(choices)
            return AgentResult(title="Creator", content=t, query=q)

        if not self.llm.use_google:
            return _fallback(level)

        prompt = (
            "Return ONLY a valid JSON object with fields 'task' and 'query'. "
            + "Level=" + level + "; Use realistic security tasks and valid KQL. "
            + "The 'task' field should be a detailed description with essential information for building the query, including:\n"
            + "- Table name (SecurityEvent or SigninLogs)\n"
            + "- Time range (e.g., last 24h, today, last 7 days)\n"
            + "- Filter criteria (EventID, ResultType, etc.)\n"
            + "- Columns to use or project\n"
            + "- Grouping/aggregation requirements\n"
            + "- Sorting/ordering requirements\n"
            + "Format the task with bullet points (•) for clarity. "
            + "Query should be a starter solution. "
            + "Do not include any markdown formatting, code blocks, or additional text. "
            + "Example format: {\"task\": \"Find failed logins\\n• Table: SecurityEvent\\n• Time: Last 24h\\n• Filter: EventID == 4625\", \"query\": \"SecurityEvent | where TimeGenerated >= ago(24h) and EventID == 4625\"}"
        )
        txt = self.llm.generate(prompt) or ""

        if not txt or not txt.strip():
            # API call failed or returned empty - use fallback
            return _fallback(level)

        # Try to extract JSON from the response (might be wrapped in markdown code blocks)
        import re
        # Remove markdown code blocks if present
        txt = re.sub(r'```json\s*', '', txt)
        txt = re.sub(r'```\s*', '', txt)
        txt = txt.strip()
        
        # Try to find JSON object in the text - more flexible pattern
        # Look for { ... "task" ... "query" ... } with any content in between
        json_match = re.search(r'\{[^{}]*(?:"task"[^{}]*"query"|"query"[^{}]*"task")[^{}]*\}', txt, re.DOTALL)
        if not json_match:
            # Try a more lenient pattern - find any JSON-like object
            json_match = re.search(r'\{.*?"task".*?"query".*?\}', txt, re.DOTALL)
        if json_match:
            txt = json_match.group(0)

        try:
            obj = json.loads(txt)
            task = obj.get("task")
            query = obj.get("query")
            if task and query:
                return AgentResult(title="Creator", content=task, query=query)
            else:
                return _fallback(level)
        except (json.JSONDecodeError, AttributeError):
            return _fallback(level)
