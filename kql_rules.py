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

def fix_query(q: str, suggested_table: str | None = None) -> str:
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
