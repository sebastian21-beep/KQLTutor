import re
from typing import List, Dict, Any
from datetime import datetime, timedelta, timezone
from schema_catalog import BASE_CATALOG

def parse_iso(dt: str) -> datetime:
    s = str(dt).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return datetime.now(timezone.utc)

def floor_time(dt: datetime, n: int, unit: str) -> datetime:
    if unit == 'm':
        floored_minute = (dt.minute // n) * n
        return dt.replace(minute=floored_minute, second=0, microsecond=0)
    if unit == 'h':
        return dt.replace(minute=0, second=0, microsecond=0)
    if unit == 'd':
        return datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc)
    return dt.replace(second=0, microsecond=0)

def strip_comments(q: str) -> str:
    return re.sub(r"//.*", "", q)

def execute_query(q: str, source: str = "static", schema_view: Any = None) -> List[Dict[str, Any]]:
    q = strip_comments(q).strip()
    stages = [p.strip() for p in q.split("|") if p.strip()]
    if not stages:
        return []
    table = stages[0]
    if table not in BASE_CATALOG:
        return []
    rows = BASE_CATALOG[table]["sample_rows"]
    if source == "dynamic" and schema_view is not None:
        rows = schema_view.sample_rows
    data = rows
    for s in stages[1:]:
        if s.startswith("where"):
            data = apply_where(data, s)
        elif s.startswith("project"):
            data = apply_project(data, s)
        elif s.startswith("extend"):
            data = apply_extend(data, s)
        elif s.startswith("distinct"):
            data = apply_distinct(data, s)
        elif s.startswith("summarize"):
            data = apply_summarize(data, s)
        elif s.startswith("order by"):
            data = apply_orderby(data, s)
        elif s.startswith("take") or s.startswith("limit"):
            m = re.search(r"(take|limit)\s+(\d+)", s)
            n = int(m.group(2)) if m else 10
            data = data[:n]
        elif s.startswith("top"):
            data = apply_top(data, s)
    return data

def apply_where(rows: List[Dict[str, Any]], clause: str) -> List[Dict[str, Any]]:
    expr = clause[len("where"):].strip()
    parts = [p.strip() for p in re.split(r"\band\b", expr, flags=re.IGNORECASE)]

    def time_threshold(p: str) -> tuple[str, datetime] | None:
        m_ago = re.match(r"(TimeGenerated|Timestamp)\s*(>=|>)\s*ago\(([^)]+)\)", p, flags=re.IGNORECASE)
        m_start = re.match(r"(TimeGenerated|Timestamp)\s*(>=|>)\s*startofday\(now\(\)\)", p, flags=re.IGNORECASE)
        if m_ago:
            unit_str = m_ago.group(3).strip()
            n = int(re.match(r"(\d+)", unit_str).group(1)) if re.match(r"(\d+)", unit_str) else 24
            if "d" in unit_str:
                delta = timedelta(days=n)
            elif "m" in unit_str:
                delta = timedelta(minutes=n)
            else:
                delta = timedelta(hours=n)
            th = datetime.now(timezone.utc) - delta
            return (m_ago.group(1), th)
        if m_start:
            now = datetime.now(timezone.utc)
            th = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
            return (m_start.group(1), th)
        return None

    def match(r: Dict[str, Any]) -> bool:
        for p in parts:
            m_eq = re.match(r'([A-Za-z0-9_]+)\s*==\s*"?([^"]+)"?', p)
            m_neq = re.match(r'([A-Za-z0-9_]+)\s*!=\s*"?([^"]+)"?', p)
            m_in = re.match(r'([A-Za-z0-9_]+)\s+in\s*\(([^)]+)\)', p)
            m_regex = re.match(r'([A-Za-z0-9_]+)\s*=~\s*"([^"]+)"', p)
            m_contains = re.match(r'([A-Za-z0-9_]+)\s+contains\s+"([^"]+)"', p)
            m_id = re.match(r"EventID\s*==\s*(\d+)", p)
            th = time_threshold(p)
            if m_eq:
                k = m_eq.group(1)
                v = m_eq.group(2)
                if str(r.get(k)) != v:
                    return False
            elif m_neq:
                k = m_neq.group(1)
                v = m_neq.group(2)
                if str(r.get(k)) == v:
                    return False
            elif m_in:
                k = m_in.group(1)
                vals_raw = [x.strip() for x in m_in.group(2).split(',')]
                vals = [v.strip('"') for v in vals_raw]
                if str(r.get(k)) not in vals:
                    return False
            elif m_regex:
                k = m_regex.group(1)
                pattern = m_regex.group(2)
                if not re.search(pattern, str(r.get(k)), re.IGNORECASE):
                    return False
            elif m_contains:
                k = m_contains.group(1)
                substr = m_contains.group(2)
                if substr.lower() not in str(r.get(k)).lower():
                    return False
            elif m_id:
                if int(r.get("EventID", -1)) != int(m_id.group(1)):
                    return False
            elif th:
                key, tval = th
                rv = r.get(key)
                if rv is None:
                    return False
                if parse_iso(str(rv)) < tval:
                    return False
        return True

    return [r for r in rows if match(r)]

def apply_project(rows: List[Dict[str, Any]], clause: str) -> List[Dict[str, Any]]:
    cols = [c.strip() for c in clause[len("project"):].split(",") if c.strip()]
    if not cols:
        return rows
    out = []
    for r in rows:
        out.append({c: r.get(c) for c in cols})
    return out

def apply_distinct(rows: List[Dict[str, Any]], clause: str) -> List[Dict[str, Any]]:
    m = re.match(r"distinct\s+([A-Za-z0-9_]+)", clause)
    if not m:
        return rows
    col = m.group(1)
    seen = set()
    out = []
    for r in rows:
        v = r.get(col)
        if v not in seen:
            seen.add(v)
            out.append({col: v})
    return out

def apply_summarize(rows: List[Dict[str, Any]], clause: str) -> List[Dict[str, Any]]:
    m_count_alias = re.match(r"summarize\s+([A-Za-z0-9_]+)\s*=\s*count\(\)\s+by\s+([A-Za-z0-9_]+)", clause)
    m_count_by = re.match(r"summarize\s+count\(\)\s+by\s+([A-Za-z0-9_]+)", clause)
    m_dcount_by = re.match(r"summarize\s+dcount\(([A-Za-z0-9_]+)\)\s+by\s+([A-Za-z0-9_]+)", clause)
    m_dcount = re.match(r"summarize\s+dcount\(([A-Za-z0-9_]+)\)", clause)
    m_count_by_bin = re.match(r"summarize\s+count\(\)\s+by\s+bin\(([A-Za-z0-9_]+)\s*,\s*(\d+)([smhd])\)", clause)
    m_count_alias_by_bin = re.match(r"summarize\s+([A-Za-z0-9_]+)\s*=\s*count\(\)\s+by\s+bin\(([A-Za-z0-9_]+)\s*,\s*(\d+)([smhd])\)", clause)
    # alias for count()
    if m_count_alias:
        alias = m_count_alias.group(1)
        col = m_count_alias.group(2)
        groups = {}
        for r in rows:
            k = r.get(col)
            groups[k] = groups.get(k, 0) + 1
        return [{col: k, alias: v} for k, v in groups.items()]
    if m_count_by:
        col = m_count_by.group(1)
        groups = {}
        for r in rows:
            k = r.get(col)
            groups[k] = groups.get(k, 0) + 1
        return [{col: k, "count": v} for k, v in groups.items()]
    if m_count_by_bin or m_count_alias_by_bin:
        if m_count_by_bin:
            col = m_count_by_bin.group(1)
            n = int(m_count_by_bin.group(2))
            unit = m_count_by_bin.group(3)
            alias = "count"
        else:
            alias = m_count_alias_by_bin.group(1)
            col = m_count_alias_by_bin.group(2)
            n = int(m_count_alias_by_bin.group(3))
            unit = m_count_alias_by_bin.group(4)
        groups = {}
        for r in rows:
            dt = parse_iso(str(r.get(col)))
            key = floor_time(dt, n, unit)
            groups[key] = groups.get(key, 0) + 1
        return [{col: k.isoformat(), alias: v} for k, v in groups.items()]
    if m_dcount_by:
        val_col = m_dcount_by.group(1)
        by_col = m_dcount_by.group(2)
        groups = {}
        for r in rows:
            k = r.get(by_col)
            groups.setdefault(k, set()).add(r.get(val_col))
        return [{by_col: k, f"dcount_{val_col}": len(v)} for k, v in groups.items()]
    if m_dcount:
        col = m_dcount.group(1)
        vals = set()
        for r in rows:
            vals.add(r.get(col))
        return [{f"dcount_{col}": len(vals)}]
    return rows

def apply_top(rows: List[Dict[str, Any]], clause: str) -> List[Dict[str, Any]]:
    m = re.match(r"top\s+(\d+)\s+by\s+([A-Za-z0-9_]+)(?:\s+(asc|desc))?", clause)
    if not m:
        return rows
    n = int(m.group(1))
    by = m.group(2)
    direction = (m.group(3) or "desc").lower()
    try:
        sorted_rows = sorted(rows, key=lambda r: r.get(by), reverse=(direction == "desc"))
    except Exception:
        sorted_rows = rows
    return sorted_rows[:n]

def apply_orderby(rows: List[Dict[str, Any]], clause: str) -> List[Dict[str, Any]]:
    m = re.match(r"order\s+by\s+([A-Za-z0-9_]+)(?:\s+(asc|desc))?", clause)
    if not m:
        return rows
    by = m.group(1)
    direction = (m.group(2) or "asc").lower()
    try:
        return sorted(rows, key=lambda r: r.get(by), reverse=(direction == "desc"))
    except Exception:
        return rows

def apply_extend(rows: List[Dict[str, Any]], clause: str) -> List[Dict[str, Any]]:
    assigns = [p.strip() for p in clause[len("extend"):].split(',') if p.strip()]
    out = []
    for r in rows:
        rr = dict(r)
        for a in assigns:
            m = re.match(r"([A-Za-z0-9_]+)\s*=\s*\"([^\"]+)\"", a)
            m2 = re.match(r"([A-Za-z0-9_]+)\s*=\s*([A-Za-z0-9_]+)", a)
            if m:
                rr[m.group(1)] = m.group(2)
            elif m2:
                rr[m2.group(1)] = rr.get(m2.group(2))
        out.append(rr)
    return out
