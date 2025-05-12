import streamlit as st
import os
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from elevenlabs.conversational_ai.conversation import Conversation
# Removed: from elevenlabs.conversational_ai.default_audio_interface import DefaultAudioInterface
from elevenlabs.types import ConversationConfig
import threading
import queue # For thread-safe communication
import traceback # For detailed error logging
from streamlit_audio_recorder import audio_recorder # Import the browser-based recorder

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
# ... (keep other tool functions)
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

# --- Callback Functions (Keep as is - they handle incoming messages) ---
def queue_agent_response(response_text):
    print(f"Callback: queue_agent_response received: {response_text[:30]}...")
    message_queue.put(("agent", response_text))

def queue_interrupted_response(original, corrected):
    print(f"Callback: queue_interrupted_response received: {corrected[:30]}...")
    message_queue.put(("interrupted", corrected))

def queue_user_transcript(transcript):
    # This callback might still be triggered if ElevenLabs performs its own VAD/transcription
    # based on the audio chunks you send, or it might become irrelevant. Monitor its behavior.
    print(f"Callback: queue_user_transcript received: {transcript[:30]}...")
    message_queue.put(("user_transcript_from_elevenlabs", transcript)) # Renamed for clarity


# --- Function to run the conversation connection/listener in a separate thread ---
# Now, this thread mainly manages the WebSocket connection lifetime and listens for server messages.
# It no longer actively captures audio using an interface.
def run_conversation_listener(conv_obj):
    try:
        print("CONV_THREAD: Conversation listener thread started.")
        # start_session now likely initializes the connection, sends config,
        # and enters a loop listening for responses from ElevenLabs.
        # It's assumed blocking until the connection ends or is closed.
        conv_obj.start_session()
        print("CONV_THREAD: start_session() returned (session presumably ended cleanly).")
        message_queue.put(("ended", "Session ended cleanly."))
    except Exception as e:
        print(f"CONV_THREAD: An error occurred in listener thread: {e}")
        print(f"CONV_THREAD: Traceback: {traceback.format_exc()}")
        message_queue.put(("error", f"Error during conversation connection: {e}"))
    finally:
        print("CONV_THREAD: Conversation listener thread finished execution block (finally).")
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
            st.session_state.conversation_log = "Initializing conversation...\n"
            st.session_state.conversation_active = True
            print("STREAMLIT_MAIN: Set conversation_active=True, log initialized.")

            prompt = ( /* Your prompt remains the same */ )
            first_message = f"Hello {user_name}, I'm your AI personal assistant..." # Your first message

            conversation_override = {"agent": {"prompt": {"prompt": prompt},"first_message": first_message,},}
            config = ConversationConfig(
                conversation_config_override=conversation_override,
                extra_body={},
                dynamic_variables={}
            )
            try:
                print("STREAMLIT_MAIN: Attempting to create ElevenLabs client and Conversation object (without audio_interface).")
                client = ElevenLabs(api_key=API_KEY)
                # !!! IMPORTANT: Initialize Conversation WITHOUT the audio_interface !!!
                conversation = Conversation(
                    client, AGENT_ID, config=config, requires_auth=True,
                    # No audio_interface parameter here
                    callback_agent_response=queue_agent_response,
                    callback_agent_response_correction=queue_interrupted_response,
                    callback_user_transcript=queue_user_transcript, # Keep other callbacks
                )
                st.session_state.conversation_object = conversation
                print("STREAMLIT_MAIN: Conversation object created successfully.")

                # Start the listener thread
                thread = threading.Thread(target=run_conversation_listener, args=(conversation,), name="ElevenLabsListenerThread")
                thread.daemon = True
                thread.start()
                print(f"STREAMLIT_MAIN: Conversation listener thread '{thread.name}' started.")
                st.rerun()

            except Exception as e:
                st.error(f"Failed to initialize or start conversation listener: {e}")
                print(f"STREAMLIT_MAIN: Exception during conversation setup: {e}\n{traceback.format_exc()}")
                st.session_state.conversation_active = False
                st.session_state.conversation_object = None
                st.session_state.conversation_log = f"Failed to initialize conversation: {e}\n"
                st.rerun()

with col2:
    if st.button("Stop Voice Assistant", disabled=not st.session_state.get("conversation_active", False), key="stop_button"):
        print("STREAMLIT_MAIN: Stop Voice Assistant button clicked.")
        if st.session_state.get("conversation_object"):
            try:
                print("STREAMLIT_MAIN: Calling conversation_object.end_session()")
                st.session_state.conversation_object.end_session()
                st.session_state.conversation_log += "\nStop request sent. Waiting for session to terminate...\n"
                st.info("Stop request sent. Waiting for confirmation via callback.")
            except Exception as e:
                st.warning(f"Error trying to explicitly end session with SDK: {e}")
                print(f"STREAMLIT_MAIN: Exception calling end_session(): {e}\n{traceback.format_exc()}")
        else:
            print("STREAMLIT_MAIN: Stop button clicked, but no active conversation object found.")
            st.session_state.conversation_active = False
        st.rerun()

# --- NEW: Audio Recorder UI ---
if st.session_state.get("conversation_active", False):
    st.markdown("---")
    st.subheader("Speak Here:")
    # Use the audio recorder component
    audio_bytes = audio_recorder(
        text="", # No button text needed, icon serves as trigger
        # energy_threshold=(-1.0, 0.1), # Adjust silence detection if needed
        pause_threshold=1.5, # Seconds of silence to end recording
        sample_rate=16000,   # Ensure this matches what your ElevenLabs agent expects
        icon_size="2x",
        key="recorder" # Add a key for stability
    )

    if audio_bytes:
        print(f"STREAMLIT_MAIN: Recorded {len(audio_bytes)} audio bytes from browser.")
        # st.audio(audio_bytes, format="audio/wav") # Optional: Play back recorded audio for debugging

        conversation_obj = st.session_state.get("conversation_object")
        if conversation_obj:
            # ---!!! Placeholder: Send audio bytes to ElevenLabs !!!---
            # This is the part that needs verification with the elevenlabs SDK documentation.
            # Does the 'Conversation' object have a method to send audio chunks?
            print("STREAMLIT_MAIN: Trying to send audio bytes (METHOD NEEDS VERIFICATION).")
            try:
                # EXAMPLE - REPLACE 'send_audio_bytes' with the ACTUAL method if it exists
                # conversation_obj.send_audio_bytes(audio_bytes)
                # If no direct method exists, you might need manual WebSocket interaction here.

                # For now, just log that user spoke and audio was captured
                message_queue.put(("user_spoke", f"(Audio bytes captured: {len(audio_bytes)})"))
                st.info("Audio sent for processing (placeholder action).") # UI feedback
                print("STREAMLIT_MAIN: Audio bytes captured - sending logic needs implementation/verification.")
                st.rerun() # Rerun to potentially clear the recorder state if needed

            except AttributeError:
                err_msg = "Conversation object doesn't have a method to directly send audio bytes."
                st.error(f"SDK Issue: {err_msg} Manual WebSocket handling might be required.")
                print(f"STREAMLIT_MAIN: {err_msg}")
                message_queue.put(("error", err_msg))
            except Exception as e:
                err_msg = f"Error sending audio data: {e}"
                st.error(err_msg)
                print(f"STREAMLIT_MAIN: {err_msg}\n{traceback.format_exc()}")
                message_queue.put(("error", err_msg))
            # ---!!! End Placeholder !!!---
        else:
            print("STREAMLIT_MAIN: Audio recorded, but no active conversation object found in state.")
            st.warning("Audio recorded, but the conversation session seems inactive.")


# --- Process Message Queue (Mostly unchanged) ---
rerun_needed_for_ui = False
processed_message_count = 0

if "conversation_log" not in st.session_state:
    st.session_state.conversation_log = ""

if not message_queue.empty():
    print(f"STREAMLIT_MAIN: Processing message queue (initial size: {message_queue.qsize()}).")

while not message_queue.empty():
    try:
        message_type, message_content = message_queue.get_nowait()
        processed_message_count += 1
        print(f"STREAMLIT_MAIN: Dequeued message: Type='{message_type}', Content='{str(message_content)[:50]}...'")

        if st.session_state.conversation_log == "Initializing conversation...\n" and message_type not in ["error", "ended", "ended_from_finally"]:
            st.session_state.conversation_log = "" # Clear "Initializing" once real content arrives

        if message_type == "agent":
            st.session_state.conversation_log += f"\n**Assistant:** {message_content}\n"
        elif message_type == "user_transcript_from_elevenlabs": # Handle transcript if SDK still provides it
             st.session_state.conversation_log += f"\n**You (Transcribed by EL):** {message_content}\n"
        elif message_type == "user_spoke": # Log indication that user spoke via browser recorder
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
            error_msg_to_log = f"\n**CONVERSATION ERROR:** {message_content}\n"
            if st.session_state.conversation_log == "Initializing conversation...\n":
                st.session_state.conversation_log = error_msg_to_log
            else:
                st.session_state.conversation_log += error_msg_to_log
            st.error(f"A conversation error occurred: {message_content}")
            st.session_state.conversation_active = False
            st.session_state.conversation_object = None
            print(f"STREAMLIT_MAIN: Processed 'error' message: {message_content}. Conversation marked inactive.")
        elif message_type == "system_debug": # Handle placeholder message
             st.session_state.conversation_log += f"\n**DEBUG:** {message_content}\n"
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
     print(f"STREAMLIT_MAIN: Processed {processed_message_count} messages in this run.")

if rerun_needed_for_ui:
    print("STREAMLIT_MAIN: Calling st.rerun() due to processed messages or state change.")
    st.rerun()


# --- Display Conversation Log (Live) ---
st.markdown("### Conversation Log")
log_display_content = st.session_state.get("conversation_log", "").strip()
final_display = log_display_content if log_display_content else "_Conversation will appear here once started._"

if final_display == "_Conversation will appear here once started._":
    st.markdown(final_display)
else:
     # Use a div for consistent display, handle "Initializing..." within the content
    st.markdown(f"<div style='height:300px;overflow-y:scroll;border:1px solid #ccc;padding:10px;font-family:monospace;white-space:pre-wrap;'>{final_display}</div>", unsafe_allow_html=True)


st.markdown("---")
st.markdown("### Simulated Tasks")
tasks_list = st.session_state.get("tasks", [])
if tasks_list:
    tasks_display_md = "\n".join([f"- {task}" for task in tasks_list])
    st.markdown(tasks_display_md)
else:
    st.markdown("_No tasks added yet._")

# Removed the st.empty() keepalive as reruns are now driven by queue processing
 print("STREAMLIT_MAIN: Reached end of script run.") # Optional final debug print