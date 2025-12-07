import os
import streamlit as st
from agents.creator import CreatorAgent
from agents.tutor import TutorAgent
from agents.fixer import FixerAgent
from agents.optimizer import OptimizerAgent
from agents.explainer import ExplainerAgent

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
if st.sidebar.button("Create task"):
    st.session_state.task = CreatorAgent(use_google=st.session_state.use_google).run({"level": st.session_state.level}).content

st.title("KQL Tutor, Fixer, Optimizer, Explainer")
col1, col2 = st.columns([2, 1])
with col1:
    st.subheader("Write KQL")
    query = st.text_area("Query", height=200, placeholder="Table | where Timestamp > ago(1h) | summarize count() by User")
    run = st.button("Analyze")
with col2:
    st.subheader("Task")
    st.write(st.session_state.task or "Click Create task to generate a goal")

if run:
    context = {
        "query": query or "",
        "task": st.session_state.task,
        "level": st.session_state.level,
    }
    tutor = TutorAgent(use_google=st.session_state.use_google).run(context)
    fixer = FixerAgent(use_google=st.session_state.use_google).run({**context, "hints": tutor.hints})
    opt = OptimizerAgent(use_google=st.session_state.use_google).run({**context, "fixed_query": fixer.query or query})
    expl = ExplainerAgent(use_google=st.session_state.use_google).run({**context, "optimized_query": opt.query or fixer.query or query})

    st.header("Output")
    o1, o2 = st.columns(2)
    with o1:
        st.subheader("Tutor hints")
        for h in tutor.hints or []:
            st.write(f"- {h}")
        st.subheader("Fixer query")
        st.code(fixer.query or "", language="kusto")
    with o2:
        st.subheader("Optimizer query")
        st.code(opt.query or "", language="kusto")
        st.subheader("Explanation")
        st.write(expl.content or "")

