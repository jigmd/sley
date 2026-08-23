import asyncio

import streamlit as st
from flow import finalization_flow, processing_flow

st.title("Sley HITL with Streamlit")

if "stage" not in st.session_state:
    st.session_state.stage = "initial"
    st.session_state.task_input = ""


def run(flow, state):
    return asyncio.run(flow.run(state))


if st.session_state.stage == "initial":
    st.header("1. Submit Data for Processing")
    task_input = st.text_area(
        "Enter data to process:", value=st.session_state.task_input, height=150
    )
    if st.button("Submit"):
        if not task_input.strip():
            st.error("Please enter some data to process.")
        else:
            # A run owns a copy of its top-level input, so keep its returned state.
            result = run(processing_flow, {"task_input": task_input})
            st.session_state.update(result)
            st.session_state.stage = "awaiting_review"
            st.rerun()

elif st.session_state.stage == "awaiting_review":
    st.header("2. Review Processed Output")
    st.code(st.session_state.processed_output)
    approve, reject = st.columns(2)

    if approve.button("Approve"):
        result = run(
            finalization_flow,
            {"processed_output": st.session_state.processed_output},
        )
        st.session_state.update(result)
        st.session_state.stage = "completed"
        st.rerun()

    if reject.button("Reject"):
        st.session_state.task_input = st.session_state.processed_output
        st.session_state.stage = "initial"
        st.rerun()

else:
    st.header("3. Task Completed")
    st.success("Task approved and completed successfully!")
    st.text_area("Final Result", value=st.session_state.final_result, disabled=True)
    if st.button("Start Over"):
        st.session_state.clear()
        st.rerun()
