import re

def analyze_kql(q: str) -> dict:
    qn = q.strip()
    hints = []
    errors = []
    optimizations = []
    if not qn:
        errors.append("Query is empty")
    if "|" not in qn:
        hints.append("Use pipe to chain operators")
    if re.search(r"summarize\s+[^|]*$", qn) and "by" not in qn:
        hints.append("Use 'summarize ... by field' for grouping")
    if re.search(r"summarize\s+count\(\)\s*$", qn) and "by" not in qn:
        hints.append("Add 'by' after count() to group")
    if re.search(r"\|\s*where\b.*\|\s*summarize\b", qn) is None and re.search(r"\|\s*summarize\b.*\|\s*where\b", qn):
        hints.append("Place where before summarize when filtering")
    if re.search(r"\|\s*project\b", qn) is None:
        optimizations.append("Project needed columns early to reduce scans")
    if re.search(r"\|\s*limit\b|\|\s*take\b", qn) is None:
        optimizations.append("Use take/limit for sampling during exploration")
    if re.search(r"distinct\b", qn) and re.search(r"\|\s*project\b", qn) is None:
        optimizations.append("Project target column then distinct for efficiency")
    if re.search(r"\|\s*where\b", qn) is None:
        hints.append("Filter early with where to reduce data")
    if re.search(r"\|\|", qn):
        errors.append("Remove duplicate pipes")
    return {"hints": hints, "errors": errors, "optimizations": optimizations}

def fix_query(q: str, suggested_table: str | None = None, task: str | None = None) -> str:
    x = q
    x = re.sub(r"\|\|+", "|", x)
    if re.search(r"\|\s*summarize\b.*\|\s*where\b", x):
        parts = [p.strip() for p in x.split("|") if p.strip()]
        parts_sorted = []
        for p in parts:
            if p.startswith("where"):
                parts_sorted.insert(1 if parts_sorted else 0, p)
            else:
                parts_sorted.append(p)
        x = " | ".join(parts_sorted)
    if re.search(r"summarize\s+count\(\)\s*$", x) and "by" not in x:
        x = re.sub(r"summarize\s+count\(\)\s*$", "summarize count() by Target", x)
    repl = suggested_table or "SecurityEvent"
    x = re.sub(r"^\s*Table\b", repl, x.strip())
    if not has_time_filter(x):
        x = insert_after_table(x, "where TimeGenerated >= ago(24h)")
    
    # Fix incorrect EventID values based on task context
    if task:
        task_lower = task.lower()
        # If task mentions failed logins/logons, ensure EventID is 4625
        if ("failed" in task_lower and ("login" in task_lower or "logon" in task_lower)) or "4625" in task:
            # Check if EventID exists but is wrong
            eventid_match = re.search(r"EventID\s*==\s*(\d+)", x, re.IGNORECASE)
            if eventid_match:
                current_eventid = eventid_match.group(1)
                if current_eventid != "4625":
                    # Replace incorrect EventID with 4625
                    x = re.sub(r"EventID\s*==\s*\d+", "EventID == 4625", x, flags=re.IGNORECASE)
            elif "eventid" not in x.lower():
                # Add EventID 4625 if missing
                # Find the where clause and add EventID filter
                where_match = re.search(r"where\s+([^|]+)", x, re.IGNORECASE)
                if where_match:
                    where_content = where_match.group(1)
                    # Add "and EventID == 4625" to the where clause
                    x = re.sub(r"(where\s+[^|]+)", r"\1 and EventID == 4625", x, flags=re.IGNORECASE, count=1)
                else:
                    # No where clause, add one after table
                    x = insert_after_table(x, "where EventID == 4625")
    
    return x.strip()

def has_time_filter(q: str) -> bool:
    return re.search(r"\b(TimeGenerated|Timestamp)\s*(>=|>)\s*ago\([^)]+\)", q, re.IGNORECASE) is not None

def insert_after_table(q: str, clause: str) -> str:
    parts = [p.strip() for p in q.split("|") if p.strip()]
    if not parts:
        return clause
    parts = [parts[0]] + ([clause] + parts[1:])
    return " | ".join(parts)

def compute_diffs(original: str, fixed: str) -> list:
    diffs = []
    o = original.strip()
    f = fixed.strip()
    o_lower = o.lower()
    f_lower = f.lower()
    if re.match(r"^\s*Table\b", o) and not re.match(r"^\s*Table\b", f):
        diffs.append("Replaced placeholder table with suggested dataset")
    if "||" in o and "||" not in f:
        diffs.append("Collapsed duplicate pipes")
    if re.search(r"\|\s*summarize\b.*\|\s*where\b", o) and re.search(r"\|\s*summarize\b.*\|\s*where\b", f) is None:
        diffs.append("Moved where before summarize")
    if re.search(r"summarize\s+count\(\)\s*$", o) and "by" not in o and re.search(r"summarize\s+count\(\)\s+by\b", f):
        diffs.append("Added 'by' to summarize count()")
    if not has_time_filter(o) and has_time_filter(f):
        diffs.append("Added TimeGenerated time filter")
    # Check for EventID corrections
    o_eventid = re.search(r"EventID\s*==\s*(\d+)", o_lower)
    f_eventid = re.search(r"EventID\s*==\s*(\d+)", f_lower)
    if o_eventid and f_eventid:
        o_val = o_eventid.group(1)
        f_val = f_eventid.group(1)
        if o_val != f_val:
            diffs.append(f"Corrected EventID from {o_val} to {f_val}")
    elif o_eventid and not f_eventid:
        # EventID was removed (shouldn't happen, but check anyway)
        pass
    elif not o_eventid and f_eventid:
        diffs.append(f"Added EventID filter: {f_eventid.group(1)}")
    return diffs

def render_commented_query(fixed: str, diffs: list) -> str:
    parts = [p.strip() for p in fixed.split("|") if p.strip()]
    annotated = []
    for p in parts:
        comment = None
        if p.startswith("SecurityEvent"):
            comment = "// choose appropriate table (e.g., SecurityEvent)"
        elif p.startswith("where") and "TimeGenerated" in p:
            comment = "// add time filter to bound data volume"
        elif p.startswith("where"):
            comment = "// filter rows before aggregation"
        elif p.startswith("project"):
            comment = "// project only needed columns to reduce scans"
        elif p.startswith("summarize"):
            comment = "// aggregate results with summarize"
        elif p.startswith("distinct"):
            comment = "// distinct values for the target column"
        line = p
        if comment:
            line = f"{p}    {comment}"
        annotated.append(line)
    header = "\n".join(["// fixes: "+", ".join(diffs)] if diffs else [])
    body = " | \n".join(annotated)
    return (header + "\n" + body).strip()

def optimize_query(q: str, task: str | None = None, relevant_columns: list | None = None, suggested_table: str | None = None) -> tuple[str, list]:
    changes = []
    x = q.strip()
    # Remove large sampling
    if re.search(r"\|\s*(take|limit)\s+\d+", x):
        x = re.sub(r"\|\s*(take|limit)\s+\d+", "", x)
        changes.append("Removed take/limit sampling")
    # Ensure time filter exists
    if not has_time_filter(x):
        x = insert_after_table(x, "where TimeGenerated >= ago(24h)")
        changes.append("Added time filter")
    # Add project to reduce columns
    cols = infer_columns(x)
    if relevant_columns:
        for c in relevant_columns:
            cols.add(c)
    if cols:
        proj = "project " + ", ".join(sorted(cols))
        if re.search(r"\|\s*project\b", x) is None:
            # insert after first where if present, else after table
            parts = [p.strip() for p in x.split("|") if p.strip()]
            inserted = False
            for i, p in enumerate(parts):
                if p.startswith("where"):
                    parts.insert(i+1, proj)
                    inserted = True
                    break
            if not inserted:
                parts = [parts[0], proj] + parts[1:]
            x = " | ".join(parts)
            changes.append("Added project to reduce columns")
    # Task-specific: distinct hosts → dcount
    if task and re.search(r"distinct\s+hosts", task, re.IGNORECASE):
        if re.search(r"distinct\s+HostName\b", x):
            x = re.sub(r"distinct\s+HostName\b", "summarize dcount(HostName)", x)
            changes.append("Replaced distinct HostName with summarize dcount(HostName)")
        elif re.search(r"summarize\b", x) is None:
            x = x + " | summarize dcount(HostName)"
            changes.append("Added summarize dcount(HostName)")
    return x.strip(), changes

def infer_columns(q: str) -> set:
    cols = set()
    # capture columns used in 'by', 'distinct', equality filters
    m_by = re.search(r"by\s+([A-Za-z0-9_]+)", q)
    if m_by:
        cols.add(m_by.group(1))
    m_dist = re.search(r"distinct\s+([A-Za-z0-9_]+)", q)
    if m_dist:
        cols.add(m_dist.group(1))
    for m in re.finditer(r"\b([A-Za-z0-9_]+)\s*(==|=~|!=|in)\s*", q):
        cols.add(m.group(1))
    cols.add("TimeGenerated")
    return cols

def explain_natural(q: str) -> tuple[str, str | None]:
    parts = [p.strip() for p in q.split("|") if p.strip()]
    table = parts[0] if parts else "(table)"
    time_clause = next((p for p in parts if p.startswith("where") and "TimeGenerated" in p), None)
    fail_clause = next((p for p in parts if re.search(r"(EventID\s*==\s*4625|LogonResult\s*==\s*\"Failed\")", p)), None)
    distinct_host = next((p for p in parts if re.search(r"distinct\s+HostName|dcount\(HostName\)", p)), None)
    s = []
    s.append(f"Step 1 selects {table} which holds relevant logs (e.g., SecurityEvent or SigninLogs).")
    if time_clause:
        s.append("Step 2 limits to a recent window using TimeGenerated >= ago(...), reducing scan cost.")
    if fail_clause:
        s.append("Step 3 filters to failed logons via LogonResult == \"Failed\" or EventID 4625.")
    if distinct_host:
        s.append("Step 4 returns unique HostName values to show machines involved.")
    if not time_clause:
        s.append("Consider adding a time filter to bound data volume.")
    classification = None
    if fail_clause:
        classification = "This is a hunting query for failed logons; you could turn it into an analytic rule by adding thresholds and scheduling."
    return " ".join(s), classification
def assess_task(task: str, q: str, schema: dict | None = None) -> tuple[bool, list, str, str]:
    mismatches = []
    fulfills = True  # Start optimistic, but check thoroughly
    reason = ""
    qn = q.strip().lower()
    t = (task or "").lower()
    suggested = (schema or {}).get("suggested_table")
    
    # Check if query is empty or too basic
    if not q or not q.strip() or len(q.strip()) < 10:
        fulfills = False
        mismatches.append("Query is empty or too basic")
        return fulfills, mismatches, q, "Query is empty or too basic"
    
    # Check table name
    if suggested and not q.strip().startswith(suggested):
        fulfills = False
        mismatches.append(f"Uses a different table than suggested ({suggested})")
    
    # Check time filters - look for various time patterns
    time_patterns = [
        r"24h", r"24\s*h", r"ago\(24h\)", r"ago\(1d\)",
        r"7d", r"7\s*d", r"ago\(7d\)",
        r"today", r"startofday",
        r"TimeGenerated\s*>=\s*ago",
        r"Timestamp\s*>=\s*ago"
    ]
    has_time = any(re.search(pattern, qn, re.IGNORECASE) for pattern in time_patterns) or has_time_filter(q)
    
    if "24h" in t or "24 hours" in t or "last 24" in t:
        if not has_time:
            fulfills = False
            mismatches.append("Missing 24h time filter (should use ago(24h) or similar)")
    elif "7d" in t or "7 days" in t or "last 7" in t:
        if not has_time:
            fulfills = False
            mismatches.append("Missing 7d time filter (should use ago(7d) or similar)")
    elif "today" in t:
        if not (has_time or "startofday" in qn):
            fulfills = False
            mismatches.append("Missing today time filter (should use startofday(now()) or similar)")
    elif any(time_word in t for time_word in ["time", "ago", "recent", "last"]):
        if not has_time:
            fulfills = False
            mismatches.append("Missing time filter")
    
    # Check for distinct hosts
    if "distinct hosts" in t or "distinct host" in t:
        if not (re.search(r"distinct\s+hostname", qn) or re.search(r"summarize\b.*hostname", qn) or re.search(r"dcount.*hostname", qn)):
            fulfills = False
            mismatches.append("Missing distinct HostName operation")
    
    # Check for failed logins
    if "failed" in t and ("login" in t or "logon" in t):
        eventid_match = re.search(r"EventID\s*==\s*(\d+)", qn)
        if eventid_match:
            eventid_value = eventid_match.group(1)
            if eventid_value != "4625":
                fulfills = False
                mismatches.append(f"Incorrect EventID {eventid_value} (should be 4625 for failed logons)")
        elif "4625" not in q and "eventid" not in qn and "resulttype" not in qn:
            fulfills = False
            mismatches.append("Missing failed login filter (EventID 4625 or ResultType)")
    
    # Check for specific aggregations mentioned in task
    if "count" in t and "per" in t:
        if "summarize" not in qn and "count()" not in qn:
            fulfills = False
            mismatches.append("Missing count aggregation (summarize count())")
    
    if "top" in t or "5" in t or "10" in t:
        if "top" not in qn and "limit" not in qn:
            fulfills = False
            mismatches.append("Missing top/limit clause")
    
    corrected = q
    if mismatches:
        corrected = fix_query(q, suggested_table=suggested, task=task)
    if fulfills:
        reason = "Query aligns with task requirements"
    else:
        reason = "Query diverges from task: " + "; ".join(mismatches)
    return fulfills, mismatches, corrected, reason
