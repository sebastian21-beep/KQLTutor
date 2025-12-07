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

def fix_query(q: str) -> str:
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
    return x.strip()

