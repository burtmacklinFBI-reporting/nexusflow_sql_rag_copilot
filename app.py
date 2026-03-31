# to run the script - streamlit run app.py

import streamlit as st
from langchain_core.messages import HumanMessage, AIMessage
from advanced_agent import app as agent_app
from dotenv import load_dotenv
load_dotenv()
import os
from langsmith import traceable

USER_AVATAR = "🧑‍💻"
BOT_AVATAR = "assets/chat_assistant.png"


@traceable(name="streamlit_chat_run", metadata={"source": "streamlit_ui"})
def run_streamlit_agent(initial_state, status_callback=None):
    final_state = None

    for output in agent_app.stream(initial_state, {"recursion_limit": 25}):
        if not output:
            continue

        for node_name, state_update in output.items():
            # 🔥 UI heartbeat (preserved)
            if status_callback:
                status_callback(node_name)

            if state_update:
                final_state = state_update

    return final_state

st.set_page_config(page_title="NexusFlow SQL Copilot", page_icon="🤖", layout="centered") # you can play around with it, change the title or add it a custom image if you want, set a background, maybe keep the message block in different colour or something like that.

# --- 1. Authentication ---
# Set your shared password here (or use an environment variable) - when you are doing local testing
SHARED_PASSWORD = os.getenv("STREAMLIT_PASSWORD")


def check_password():
    """Returns `True` if the user had the correct password."""
    if st.session_state.get("password_correct", False): # if false it will not return false.
        return True

    st.title("🔒 Login Required")
    st.markdown("Please enter your password to access the NexusFlow SQL Copilot:")
    
    password = st.text_input("Password", type="password", key="pwd_input") # normal type which is default would show what you are typing but the password would actually make it masked.


#     🔑 6.3 key="pwd_input" (VERY IMPORTANT)

# This is critical in Streamlit.

# 👉 It uniquely identifies this widget in session_state

# Without key:

# Streamlit tries to infer identity from:

# Position in code
# Label

# 👉 Can break if UI changes

# With key:
# st.session_state["pwd_input"]

# 👉 Always maps to this input
    
    if st.button("Login"):  # here rerun happenns, and the value of this in the state will become True
        if password == SHARED_PASSWORD:
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("😕 Password incorrect")
            
    return False

if not check_password():
    st.stop()  # Do not continue if check_password is False

# --- 2. Main App UI ---
st.title("🧠 NexusFlow SQL Copilot")
st.markdown("Ask natural language questions about your revenue data, metrics, and business policies.")

# Initialize UI chat history in session state
if "messages" not in st.session_state:
    st.session_state.messages = []
    # Add an initial greeting
    st.session_state.messages.append(
        AIMessage(content="Hello! I am your NexusFlow RevOps Copilot. How can I help you today?")
    )

# Initialize the LangChain message history (what we send to the agent)
if "agent_history" not in st.session_state:
    st.session_state.agent_history = [] # agent history would never have the opening message. Order is preserved in lists unlike sets so we should be good.

# Display chat messages from history on app rerun
for msg in st.session_state.messages:
    role = "user" if isinstance(msg, HumanMessage) else "assistant"
    avatar = USER_AVATAR if role == "user" else BOT_AVATAR
    with st.chat_message(role,avatar=avatar):
        st.markdown(msg.content)


# you can do custom changing of the avatars like this 


# with st.chat_message("user", avatar="🧑‍💻"):
#     st.markdown(prompt)

# with st.chat_message("assistant", avatar="🧠"):
#     st.markdown(response)

# avatar="🧑‍💻"   # developer vibe
# avatar="📊"     # data analyst
# avatar="🤖"     # AI bot
# avatar="🧠"     # your brand (nice for NexusFlow)
# avatar="⚡"     # fast assistant feel


# or like this with st.chat_message("assistant", avatar="logo.png"):


# Accept user input
if prompt := st.chat_input("Ask a data question..."):  ## 🔴 check how it would submit the prompt and also do check how will it react when I do not enter something and then I would click on enter?
    # Display user message in chat message container
    with st.chat_message("user",avatar=USER_AVATAR):
        st.markdown(prompt)
        
    # Add user message to UI history
    st.session_state.messages.append(HumanMessage(content=prompt))
    
    # Prepare the initial state for the agent
    initial_state = {
        "question": prompt,
        "messages": st.session_state.agent_history + [HumanMessage(content=prompt)],
        "retry_count": 0,
        "safety_passed": False,
        "error": {},
        "rewritten_question": None,
        "hybrid_context": None,
        "structural_context": None,
        "style_guide_context": None,
        "generated_sql": None,
        "sql_result": None,
        "final_context": None,
        "final_answer_clean": None,
        "total_retry_count": 0,
        "sql_repeat_count": 0
    }
    
    # Display assistant response in chat message container
    with st.chat_message("assistant",avatar=BOT_AVATAR):
        status_placeholder = st.empty() # it is like a box that can be updated with values that we want.
        
        final_state = None
        try:
            with st.spinner("Analyzing request..."):

                def update_status(node_name):
                    status_placeholder.info(f"⚙️ Processing stage: `{node_name}`...")

                final_state = run_streamlit_agent(
                    initial_state,
                    status_callback=update_status
                )
            
            # Clear the status text
            status_placeholder.empty()
            
            # Process the final state to get the response
            if final_state and final_state.get("messages"):
                # Get the last message from the agent
                agent_response = final_state["messages"][-1]
                
                # Use final_answer_clean if available (it strips out the SQL thought process for a cleaner UI)
                clean_answer = final_state.get("final_answer_clean")
                
                # Determine what to show to the user and what to save to history
                # display_content = clean_answer if clean_answer else agent_response.content
                display_content = agent_response.content
                                
                # Append to UI history
                if display_content:
                  st.session_state.messages.append(AIMessage(content=display_content))
                  st.markdown(display_content)
                else:
                  st.session_state.messages.append(AIMessage(content=clean_answer))
                  st.markdown(clean_answer)

                
                # Append to Agent internal history (keeping the context pure)
                st.session_state.agent_history.append(HumanMessage(content=prompt))
  # for the agent we will give the cleaned one but for the user we will provide the entire data.
                if clean_answer:
                  st.session_state.agent_history.append(AIMessage(content=clean_answer))
                else:
                  st.session_state.agent_history.append(AIMessage(content=display_content))
                  

            elif final_state and any(v for v in final_state.get("error", {}).values()):
                # Format the error nicely
                error_dict = final_state.get("error", {})
                error_msg = f"⚠️ **Error encountered:**\n\n```json\n{error_dict}\n```"
                st.error("I encountered an issue processing your request.")
                st.markdown(error_msg)
                st.session_state.messages.append(AIMessage(content=error_msg))
            else:
                fallback = "Sorry, something went wrong and I couldn't generate a response."
                st.error(fallback)
                st.session_state.messages.append(AIMessage(content=fallback))
                
        except Exception as e:
            st.error(f"An unexpected error occurred: {str(e)}")
