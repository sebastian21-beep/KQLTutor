import os
import streamlit as st
from dotenv import load_dotenv
import google.generativeai as genai
from agents.creator import CreatorAgent
from agents.tutor import TutorAgent
from agents.fixer import FixerAgent
from agents.optimizer import OptimizerAgent
from agents.explainer import ExplainerAgent
from agents.schema import SchemaAgent
from agents.evaluator import EvaluatorAgent
from kql_exec import execute_query

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))
API_KEY = os.environ.get("GOOGLE_API_KEY")
if API_KEY:
    genai.configure(api_key=API_KEY)

st.set_page_config(page_title="KQL Playground", page_icon="🧠", layout="wide")

if "task" not in st.session_state:
    st.session_state.task = None
if "level" not in st.session_state:
    st.session_state.level = "Easy"
if "use_google" not in st.session_state:
    st.session_state.use_google = bool(API_KEY)

st.sidebar.title("KQL Playground")
st.sidebar.selectbox("Task level", ["Easy", "Intermediate"], key="level")
st.sidebar.checkbox("Use Google AI SDK", key="use_google")
st.sidebar.selectbox("Query source", ["Static (base)", "Dynamic (task view)"], key="query_source")

# Debug info
if st.sidebar.checkbox("Show debug info", key="show_debug"):
    st.sidebar.write(f"use_google: {st.session_state.use_google}")
    st.sidebar.write(f"API_KEY set: {bool(API_KEY)}")
    if st.session_state.use_google:
        import google.generativeai as genai
        genai.configure(api_key=API_KEY)
        try:
            models = genai.list_models()
            available = []
            for m in models:
                if hasattr(m, 'supported_generation_methods') and 'generateContent' in m.supported_generation_methods:
                    name = m.name
                    if name.startswith('models/'):
                        name = name[7:]
                    available.append(name)
            st.sidebar.write(f"Available models: {', '.join(available) if available else 'None found'}")
        except Exception as e:
            st.sidebar.error(f"Error listing models: {e}")
        
        from agents.base import LLMClient
        test_client = LLMClient(use_google=True)
        st.sidebar.write(f"LLMClient.use_google: {test_client.use_google}")
        st.sidebar.write(f"LLMClient.model: {test_client.model is not None}")
        if hasattr(test_client, '_model_name'):
            st.sidebar.write(f"Selected model: {test_client._model_name}")
        if hasattr(test_client, '_last_error') and test_client._last_error:
            st.sidebar.error(f"Error: {test_client._last_error}")
        # Test API call
        if test_client.model:
            test_result = test_client.generate("Say 'test'")
            st.sidebar.write(f"Test API call result: {test_result[:50] if test_result else 'None'}")
            if hasattr(test_client, '_last_error') and test_client._last_error:
                st.sidebar.error(f"API Error: {test_client._last_error}")

if st.sidebar.button("Create task"):
    cr = CreatorAgent(use_google=st.session_state.use_google).run({"level": st.session_state.level})
    st.session_state.task = cr.content
    st.session_state.starter_query = cr.query
    st.session_state.query_input = cr.query or st.session_state.get("query_input", "")
    st.session_state.schema_view = SchemaAgent(use_google=st.session_state.use_google).compute(st.session_state.task or "")

st.title("KQL Tutor, Fixer, Optimizer, Explainer")
col1, col2 = st.columns([2, 1])
with col1:
    st.subheader("Write KQL")
    query = st.text_area("Query", height=200, placeholder="Table | where Timestamp > ago(1h) | summarize count() by User", key="query_input", value=st.session_state.get("query_input", ""))
    run = st.button("Analyze")
with col2:
    st.subheader("Task")
    task_text = st.session_state.task or "Click Create task to generate a goal"
    
    if task_text and task_text != "Click Create task to generate a goal":
        # Split task into title and details
        lines = task_text.split("\n")
        task_title = lines[0] if lines else task_text
        task_details = "\n".join(lines[1:]) if len(lines) > 1 else ""
        
        # Show task title
        st.write(task_title)
        
        # Show hint button and details in expander
        if task_details and "•" in task_details:
            with st.expander("💡 Hint - Show task details", expanded=False):
                # Convert bullet points to markdown format
                formatted_details = task_details.replace("•", "-")
                st.markdown(formatted_details)
        elif task_details:
            with st.expander("💡 Hint - Show task details", expanded=False):
                st.markdown(task_details)
    else:
        st.write(task_text)
    if "starter_query" in st.session_state and st.session_state.starter_query:
        st.subheader("Suggested start query")
        st.code(st.session_state.starter_query, language="kusto")
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
    
    # Step 1: Run EvaluatorAgent first to evaluate if query fulfills task
    evaluator = EvaluatorAgent(use_google=st.session_state.use_google).run({
        **context,
        "schema": schema_dict
    })
    
    # Step 2: Run all other agents in parallel with evaluation result
    from concurrent.futures import ThreadPoolExecutor
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        # Submit all agent tasks in parallel with evaluation result
        tutor_future = executor.submit(
            TutorAgent(use_google=st.session_state.use_google).run,
            {**context, "schema": schema_dict, "evaluation": evaluator}
        )
        fixer_future = executor.submit(
            FixerAgent(use_google=st.session_state.use_google).run,
            {**context, "schema": schema_dict, "evaluation": evaluator}
        )
        opt_future = executor.submit(
            OptimizerAgent(use_google=st.session_state.use_google).run,
            {**context, "schema": schema_dict, "fixed_query": query, "evaluation": evaluator}
        )
        expl_future = executor.submit(
            ExplainerAgent(use_google=st.session_state.use_google).run,
            {**context, "schema": schema_dict, "optimized_query": query, "evaluation": evaluator}
        )
        
        # Wait for all agents to complete (their LLM calls run in parallel)
        tutor = tutor_future.result()
        fixer = fixer_future.result()
        opt = opt_future.result()
        expl = expl_future.result()

    st.header("Output")
    
    # Show evaluation result at the top
    st.subheader("Task Evaluation")
    if evaluator.fulfills_task is not None:
        st.write(f"**Query fulfills task:** {'✅ Yes' if evaluator.fulfills_task else '❌ No'}")
    if evaluator.reason:
        if "**" in evaluator.reason:
            st.markdown(evaluator.reason)
        else:
            st.write(evaluator.reason)
    st.divider()
    
    o1, o2 = st.columns(2)
    with o1:
        st.subheader("Tutor lesson")
        if tutor.content:
            # Check if content has markdown formatting
            if "**" in tutor.content or "Relevance to Task" in tutor.content:
                st.markdown(tutor.content)
            else:
                st.write(tutor.content)
        st.subheader("Tutor hints")
        for h in tutor.hints or []:
            st.write(f"- {h}")
        st.subheader("Alternative patterns")
        for a in tutor.suggestions or []:
            st.write(f"- {a}")
        st.subheader("Task vs Query")
        # Use evaluator's result (already shown at top, but show fixer's corrections here)
        if fixer.reason and "Task Coverage" in fixer.reason:
            # Check if reason has markdown formatting
            if "**" in fixer.reason:
                st.markdown(fixer.reason)
            else:
                st.write(fixer.reason)
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
        if opt.content and "Task Alignment" in opt.content:
            st.markdown(opt.content)
        st.subheader("Explanation")
        if expl.content:
            # Check if content has markdown formatting
            if "**" in expl.content or "Connection to Task" in expl.content:
                st.markdown(expl.content)
            else:
                st.write(expl.content)
        if expl.hints:
            for h in expl.hints:
                st.write(h)

