import os
import streamlit as st
from agents.creator import CreatorAgent
from agents.tutor import TutorAgent
from agents.fixer import FixerAgent
from agents.optimizer import OptimizerAgent
from agents.explainer import ExplainerAgent
from agents.schema import SchemaAgent
from kql_exec import execute_query

st.set_page_config(page_title="KQL Playground", page_icon="🧠", layout="wide")

if "task" not in st.session_state:
    st.session_state.task = None
if "level" not in st.session_state:
    st.session_state.level = "Easy"
if "use_google" not in st.session_state:
    st.session_state.use_google = False

st.sidebar.title("KQL Playground")
st.sidebar.selectbox("Task level", ["Easy", "Intermediate"], key="level")
st.sidebar.checkbox("Use Google AI SDK", key="use_google")
st.sidebar.selectbox("Query source", ["Static (base)", "Dynamic (task view)"], key="query_source")
if st.sidebar.button("Create task"):
    st.session_state.task = CreatorAgent(use_google=st.session_state.use_google).run({"level": st.session_state.level}).content
    st.session_state.schema_view = SchemaAgent(use_google=st.session_state.use_google).compute(st.session_state.task or "")

st.title("KQL Tutor, Fixer, Optimizer, Explainer")
col1, col2 = st.columns([2, 1])
with col1:
    st.subheader("Write KQL")
    query = st.text_area("Query", height=200, placeholder="Table | where Timestamp > ago(1h) | summarize count() by User")
    run = st.button("Analyze")
    run_query = st.button("Query")
with col2:
    st.subheader("Task")
    st.write(st.session_state.task or "Click Create task to generate a goal")
    if "schema_view" in st.session_state and st.session_state.schema_view:
        sv = st.session_state.schema_view
        st.subheader("Schema view")
        st.write(f"Suggested table: {sv.suggested_table}")
        st.write(sv.reason)
        st.write("Relevant columns:")
        st.write(", ".join(sv.relevant_columns))
        st.subheader("Sample rows")
        try:
            import pandas as pd
            df = pd.DataFrame(sv.sample_rows[:3])
            st.dataframe(df)
        except Exception:
            for r in sv.sample_rows[:3]:
                st.write(r)

if run:
    context = {
        "query": query or "",
        "task": st.session_state.task,
        "level": st.session_state.level,
    }
    schema_view = st.session_state.get("schema_view")
    schema_dict = None
    if schema_view:
        schema_dict = {
            "suggested_table": schema_view.suggested_table,
            "reason": schema_view.reason,
            "relevant_columns": schema_view.relevant_columns,
            "sample_rows": schema_view.sample_rows[:3],
        }
    tutor = TutorAgent(use_google=st.session_state.use_google).run({**context, "schema": schema_dict})
    fixer = FixerAgent(use_google=st.session_state.use_google).run({**context, "schema": schema_dict, "hints": tutor.hints})
    opt = OptimizerAgent(use_google=st.session_state.use_google).run({**context, "schema": schema_dict, "fixed_query": fixer.query or query})
    expl = ExplainerAgent(use_google=st.session_state.use_google).run({**context, "schema": schema_dict, "optimized_query": opt.query or fixer.query or query})

    st.header("Output")
    o1, o2 = st.columns(2)
    with o1:
        st.subheader("Tutor lesson")
        if tutor.content:
            st.write(tutor.content)
        st.subheader("Tutor hints")
        for h in tutor.hints or []:
            st.write(f"- {h}")
        st.subheader("Alternative patterns")
        for a in tutor.suggestions or []:
            st.write(f"- {a}")
        st.subheader("Fixer changes")
        for d in fixer.suggestions or []:
            st.write(f"- {d}")
        st.subheader("Fixed query (commented)")
        st.code(fixer.query or "", language="kusto")
    with o2:
        st.subheader("Optimizer: Before vs After")
        st.write("Before:")
        st.code(fixer.query or query or "", language="kusto")
        st.write("After:")
        st.code(opt.query or "", language="kusto")
        st.subheader("Optimizer changes")
        for s in opt.suggestions or []:
            st.write(f"- {s}")
        st.subheader("Explanation")
        st.write(expl.content or "")
        if expl.hints:
            for h in expl.hints:
                st.write(h)

if 'run_query' in locals() and run_query:
    schema_view = st.session_state.get("schema_view")
    source = "static" if st.session_state.query_source.startswith("Static") else "dynamic"
    exec_schema = schema_view if source == "dynamic" else None
    context = {
        "query": query or "",
        "task": st.session_state.task,
        "level": st.session_state.level,
    }
    fixer = FixerAgent(use_google=st.session_state.use_google).run({**context, "schema": {
        "suggested_table": schema_view.suggested_table if schema_view else None,
        "relevant_columns": schema_view.relevant_columns if schema_view else None,
    }})
    opt = OptimizerAgent(use_google=st.session_state.use_google).run({**context, "schema": {
        "suggested_table": schema_view.suggested_table if schema_view else None,
        "relevant_columns": schema_view.relevant_columns if schema_view else None,
    }, "fixed_query": fixer.query or query})
    run_q = opt.query or fixer.query or query
    try:
        import pandas as pd
        rows = execute_query(run_q, source=source, schema_view=schema_view)
        if rows:
            st.subheader("Query Results")
            st.caption(f"Source: {st.session_state.query_source}")
            st.dataframe(pd.DataFrame(rows))
        else:
            st.subheader("Query Results")
            st.write("No rows")
    except Exception as e:
        st.subheader("Query Results")
        st.write("Error executing query")
