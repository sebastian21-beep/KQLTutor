from .base import AgentResult, LLMClient
import random

class CreatorAgent:
    def __init__(self, use_google: bool = False):
        self.llm = LLMClient(use_google)

    def run(self, context: dict) -> AgentResult:
        level = context.get("level", "Easy")
        easy = [
            "Count events in last hour grouped by Source",
            "Top 5 users by event count today",
            "Distinct hosts with failed logins in 24h",
        ]
        intermediate = [
            "Daily trend of errors per service in 7d",
            "Top IPs by bytes with threshold and percent",
            "Join login failures with user roles and summarize",
        ]
        tasks = easy if level == "Easy" else intermediate
        t = random.choice(tasks)
        return AgentResult(title="Creator", content=t)

