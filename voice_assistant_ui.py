import streamlit as st
import os
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from elevenlabs.conversational_ai.conversation import Conversation
from elevenlabs.conversational_ai.default_audio_interface import DefaultAudioInterface
from elevenlabs.types import ConversationConfig
import threading
import queue # For thread-safe communication
import traceback # For detailed error logging

# Load environment variables
load_dotenv()
AGENT_ID = os.getenv("AGENT_ID")
API_KEY = os.getenv("API_KEY")

# --- Thread-safe Queue for messages from callbacks ---
message_queue = queue.Queue()

# --- Top-level Session State Initialization ---
if "conversation_log" not in st.session_state:
    st.session_state.conversation_log = ""
    print("Initialized st.session_state.conversation_log")
if "tasks" not in st.session_state:
    st.session_state.tasks = []
if "conversation_active" not in st.session_state:
    st.session_state.conversation_active = False
    print("Initialized st.session_state.conversation_active")
if "conversation_object" not in st.session_state:
    st.session_state.conversation_object = None

# --- Placeholder Tool Functions (Keep as is) ---
def get_calendar_events(date_str: str):
    print(f"[Tool Sim] Attempting to fetch calendar events for {date_str}...")
    if "today" in date_str.lower():
        return "Based on a hypothetical calendar: Sales Meeting with Taipy at 10:00; Gym with Sophie at 17:00."
    return "I'm not yet fully connected to a live calendar to fetch specific dates."

def add_calendar_event(summary: str, start_time_str: str, end_time_str: str = None):
    print(f"[Tool Sim] Attempting to add calendar event: {summary} at {start_time_str}...")
    return f"Okay, I've made a note to schedule '{summary}' at {start_time_str}. (This is a simulation)"

def search_web(query: str):
    print(f"[Tool Sim] Attempting to search web for: {query}...")
    if "weather in london" in query.lower():
        return "According to a quick search, it's usually mild in London, but check a live source for today!"
    return f"I found some information about '{query}', but I'm still learning to summarize it well."

def get_recipe(dish_name: str):
    print(f"[Tool Sim] Attempting to find recipe for: {dish_name}...")
    if "pasta" in dish_name.lower():
        return f"For {dish_name}, you'll typically need pasta, tomato sauce, garlic, and olive oil. Cook pasta, prepare sauce, combine and serve!"
    return f"I'd love to find a recipe for {dish_name}, but my cookbook is currently offline."

def add_task(task_description: str):
    print(f"[Tool Sim] Attempting to add task: {task_description}...")
    if "tasks" not in st.session_state:
        st.session_state.tasks = []
    st.session_state.tasks.append(task_description)
    return f"Task '{task_description}' has been noted."

def get_tasks():
    print(f"[Tool Sim] Attempting to retrieve tasks...")
    if "tasks" not in st.session_state or not st.session_state.tasks:
        return "You have no active tasks noted."
    tasks_str = "; ".join(st.session_state.tasks)
    return f"Your current tasks are: {tasks_str}."

# --- Callback Functions (Keep as is) ---
def queue_agent_response(response_text):
    print(f"Callback: queue_agent_response received: {response_text[:30]}...")
    message_queue.put(("agent", response_text))

def queue_interrupted_response(original, corrected):
    print(f"Callback: queue_interrupted_response received: {corrected[:30]}...")
    message_queue.put(("interrupted", corrected))

def queue_user_transcript(transcript):
    print(f"Callback: queue_user_transcript received: {transcript[:30]}...")
    message_queue.put(("user", transcript))

# --- Function to run the conversation in a separate thread (Keep as is) ---
def run_conversation_session(conv_obj):
    try:
        print("CONV_THREAD: Conversation thread started.")
        conv_obj.start_session()
        print("CONV_THREAD: start_session() returned (session presumably ended cleanly).")
        message_queue.put(("ended", "Session ended cleanly."))
    except Exception as e:
        print(f"CONV_THREAD: An error occurred in start_session() or during conversation: {e}")
        print(f"CONV_THREAD: Traceback: {traceback.format_exc()}")
        message_queue.put(("error", f"Error during conversation: {e}"))
    finally:
        print("CONV_THREAD: Conversation thread finished execution block (finally).")
        message_queue.put(("ended_from_finally", "Session processing finished in thread."))


# --- Streamlit UI ---
st.set_page_config(page_title="Voice Assistant", layout="centered")
st.title("🎙️ Your AI Personal Assistant")

print(f"STREAMLIT_MAIN: Script run. Conversation Active: {st.session_state.get('conversation_active')}, Queue size: {message_queue.qsize()}")


user_name = st.text_input("Your Name", "Alex")
schedule_input = st.text_area("Today's Schedule (for initial context)", "Sales Meeting with Taipy at 10:00; Gym with Sophie at 17:00")

col1, col2 = st.columns(2)
with col1:
    if st.button("Start Voice Assistant", disabled=st.session_state.get("conversation_active", False), key="start_button"):
        print("STREAMLIT_MAIN: Start Voice Assistant button clicked.")
        if not AGENT_ID or not API_KEY:
            st.error("AGENT_ID or API_KEY is not set. Please check your .env file.")
            print("STREAMLIT_MAIN: Missing AGENT_ID or API_KEY.")
        else:
            # Reset log for a new conversation, starting with "Initializing..."
            st.session_state.conversation_log = "Initializing conversation...\n"
            st.session_state.conversation_active = True
            print("STREAMLIT_MAIN: Set conversation_active=True, log initialized to 'Initializing...'.")

            prompt = (
                f"You are a highly capable AI personal assistant for {user_name}. "
                f"Your primary functions include: Scheduling and managing appointments, answering queries by searching the web, "
                f"providing cooking instructions, and managing daily tasks. "
                f"Your interlocutor, {user_name}, has the following initial schedule: {schedule_input}. "
            )
            first_message = f"Hello {user_name}, I'm your AI personal assistant. Today's schedule I have for you is: {schedule_input}. How can I help you further?"

            conversation_override = {"agent": {"prompt": {"prompt": prompt},"first_message": first_message,},}
            config = ConversationConfig(
                conversation_config_override=conversation_override,
                extra_body={},
                dynamic_variables={}
            )
            try:
                print("STREAMLIT_MAIN: Attempting to create ElevenLabs client and Conversation object.")
                client = ElevenLabs(api_key=API_KEY)
                conversation = Conversation(
                    client, AGENT_ID, config=config, requires_auth=True,
                    audio_interface=DefaultAudioInterface(),
                    callback_agent_response=queue_agent_response,
                    callback_agent_response_correction=queue_interrupted_response,
                    callback_user_transcript=queue_user_transcript,
                )
                st.session_state.conversation_object = conversation
                print("STREAMLIT_MAIN: Conversation object created successfully.")

                thread = threading.Thread(target=run_conversation_session, args=(conversation,), name="ElevenLabsConversationThread")
                thread.daemon = True
                thread.start()
                print(f"STREAMLIT_MAIN: Conversation thread '{thread.name}' started.")
                # No st.info here, the log will show "Initializing..."
                st.rerun()

            except Exception as e:
                st.error(f"Failed to initialize or start conversation: {e}")
                print(f"STREAMLIT_MAIN: Exception during conversation setup: {e}\n{traceback.format_exc()}")
                st.session_state.conversation_active = False
                st.session_state.conversation_object = None
                # Update log to show error if setup failed
                st.session_state.conversation_log = f"Failed to initialize conversation: {e}\n"
                st.rerun() # Rerun to show the error in the log

with col2:
    if st.button("Stop Voice Assistant", disabled=not st.session_state.get("conversation_active", False), key="stop_button"):
        print("STREAMLIT_MAIN: Stop Voice Assistant button clicked.")
        if st.session_state.get("conversation_object"):
            try:
                print("STREAMLIT_MAIN: Calling conversation_object.end_session()")
                st.session_state.conversation_object.end_session()
                # The conversation thread should detect this and queue an "ended" message.
                # We can add a message to the log directly for immediate feedback
                st.session_state.conversation_log += "\nStop request sent. Waiting for session to terminate...\n"
                st.info("Stop request sent. Waiting for full termination via callback.")
            except Exception as e:
                st.warning(f"Error trying to explicitly end session with SDK: {e}")
                print(f"STREAMLIT_MAIN: Exception calling end_session(): {e}\n{traceback.format_exc()}")
        else:
            print("STREAMLIT_MAIN: Stop button clicked, but no active conversation object found.")
            st.session_state.conversation_active = False # Ensure it's marked inactive
        st.rerun()


# --- Process Message Queue (in the main Streamlit thread) ---
rerun_needed_for_ui = False
processed_message_count = 0

# Initialize log if it's somehow missing (defensive)
if "conversation_log" not in st.session_state:
    st.session_state.conversation_log = ""

# Check if the log is still "Initializing..." and the queue has messages.
# If so, we should clear "Initializing..." before appending actual conversation.
if st.session_state.conversation_log == "Initializing conversation...\n" and not message_queue.empty():
    # Check if the first message is NOT an error or premature end
    # This logic might be too complex; simpler to just append.
    # For now, let's assume appending is fine and "Initializing..." will be scrolled away.
    pass


if not message_queue.empty():
    print(f"STREAMLIT_MAIN: Processing message queue (initial size: {message_queue.qsize()}).")

while not message_queue.empty():
    try:
        message_type, message_content = message_queue.get_nowait()
        processed_message_count += 1
        print(f"STREAMLIT_MAIN: Dequeued message: Type='{message_type}', Content='{str(message_content)[:50]}...'")

        # If the log is currently "Initializing...", clear it before adding the first real message,
        # unless the first message is an error that should replace it.
        if st.session_state.conversation_log == "Initializing conversation...\n" and message_type != "error":
            st.session_state.conversation_log = ""


        if message_type == "agent":
            st.session_state.conversation_log += f"\n**Assistant:** {message_content}\n"
        elif message_type == "user":
            st.session_state.conversation_log += f"\n**You:** {message_content}\n"
        elif message_type == "interrupted":
            st.session_state.conversation_log += f"\n**Assistant (interrupted, truncated):** {message_content}\n"
        elif message_type == "ended" or message_type == "ended_from_finally":
            log_message = message_content if message_content else "Session ended."
            if st.session_state.get("conversation_active", True):
                 st.session_state.conversation_log += f"\n{log_message}\n"
                 st.session_state.conversation_active = False
                 st.session_state.conversation_object = None
                 print(f"STREAMLIT_MAIN: Processed '{message_type}' message. Conversation marked inactive.")
            else:
                print(f"STREAMLIT_MAIN: Processed '{message_type}' message, but conversation already inactive.")
        elif message_type == "error":
            # Replace "Initializing..." or append error.
            error_msg_to_log = f"\n**CONVERSATION ERROR:** {message_content}\n"
            if st.session_state.conversation_log == "Initializing conversation...\n":
                st.session_state.conversation_log = error_msg_to_log
            else:
                st.session_state.conversation_log += error_msg_to_log

            st.error(f"A conversation error occurred: {message_content}")
            st.session_state.conversation_active = False
            st.session_state.conversation_object = None
            print(f"STREAMLIT_MAIN: Processed 'error' message: {message_content}. Conversation marked inactive.")
        else:
            print(f"STREAMLIT_MAIN: Unknown message type in queue: {message_type}")

        rerun_needed_for_ui = True
    except queue.Empty:
        print("STREAMLIT_MAIN: Message queue became empty during processing loop.")
        break
    except Exception as e:
        print(f"STREAMLIT_MAIN: Error processing message queue item: {e}\n{traceback.format_exc()}")
        st.session_state.conversation_log += f"\n**System Error processing queue message:** {e}\n"
        rerun_needed_for_ui = True

if processed_message_count > 0:
     print(f"STREAMLIT_MAIN: Processed {processed_message_count} messages in this run. Log snippet: '{st.session_state.get('conversation_log', '')[-100:]}'")

if rerun_needed_for_ui:
    print("STREAMLIT_MAIN: Calling st.rerun() due to processed messages or state change.")
    st.rerun()


# --- Display Conversation Log (Live) ---
st.markdown("### Conversation Log")
log_display_content = st.session_state.get("conversation_log", "").strip()

if not log_display_content: # If log is empty or only whitespace
    final_display = "_Conversation will appear here once started._"
elif log_display_content == "Initializing conversation...": # If it's *still* only initializing
    final_display = "Initializing conversation..."
else: # Actual content exists
    final_display = log_display_content

# Render the final_display
if final_display == "_Conversation will appear here once started._" or final_display == "Initializing conversation...":
    st.markdown(final_display)
else:
    st.markdown(f"<div style='height:300px;overflow-y:scroll;border:1px solid #ccc;padding:10px;font-family:monospace;white-space:pre-wrap;'>{final_display}</div>", unsafe_allow_html=True)


st.markdown("---")
st.markdown("### Simulated Tasks")
tasks_list = st.session_state.get("tasks", [])
if tasks_list:
    tasks_display_md = "\n".join([f"- {task}" for task in tasks_list])
    st.markdown(tasks_display_md)
else:
    st.markdown("_No tasks added yet._")

if st.session_state.get("conversation_active", False):
    st.empty()
    print("STREAMLIT_MAIN: Conversation active, rendered st.empty() for potential refresh trigger.")