from dataclasses import dataclass
from typing import List, Dict, Any
from .base import AgentResult, LLMClient
from schema_catalog import BASE_CATALOG

@dataclass
class SchemaView:
    suggested_table: str
    reason: str
    relevant_columns: List[str]
    sample_rows: List[Dict[str, Any]]

class SchemaAgent:
    def __init__(self, use_google: bool = False):
        self.llm = LLMClient(use_google)

    def run(self, task: str) -> AgentResult:
        view = self._build_view(task or "")
        content = {
            "suggested_table": view.suggested_table,
            "reason": view.reason,
            "relevant_columns": view.relevant_columns,
            "sample_rows": view.sample_rows[:3],
        }
        return AgentResult(title="Schema", content=str(content), hints=None, suggestions=None)

    def compute(self, task: str) -> SchemaView:
        return self._build_view(task or "")

    def _build_view(self, task: str) -> SchemaView:
        t = task.lower()
        if any(k in t for k in ["sign-in", "signin", "signins"]):
            table = "SigninLogs"
            base_cols = BASE_CATALOG[table]["columns"]
            cols = ["TimeGenerated", "UserPrincipalName", "IPAddress", "ResultType"]
            reason = "Task mentions sign-ins → use SigninLogs with ResultType"
        else:
            table = "SecurityEvent"
            base_cols = BASE_CATALOG[table]["columns"]
            cols = ["TimeGenerated", "HostName", "EventID", "LogonResult"]
            if "host" in t and "HostName" not in cols:
                cols.append("HostName")
            if any(k in t for k in ["failed", "4625", "logon"]):
                reason = "Task mentions failed logins → use SecurityEvent with EventID 4625"
            else:
                reason = "Default to SecurityEvent for authentication-related tasks"
        if "user" in t:
            if table == "SecurityEvent" and "Account" in base_cols and "Account" not in cols:
                cols.append("Account")
            if table == "SigninLogs" and "UserPrincipalName" in base_cols and "UserPrincipalName" not in cols:
                cols.append("UserPrincipalName")
        if "ip" in t:
            ip_col = "IpAddress" if table == "SecurityEvent" else "IPAddress"
            if ip_col in base_cols and ip_col not in cols:
                cols.append(ip_col)
        cols = [c for c in cols if c in base_cols]
        rows = BASE_CATALOG[table]["sample_rows"]
        return SchemaView(table, reason, cols, rows)
