import streamlit as st
import os
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from elevenlabs.conversational_ai.conversation import Conversation
from elevenlabs.conversational_ai.default_audio_interface import DefaultAudioInterface
from elevenlabs.types import ConversationConfig
# from elevenlabs.client import ElevenLabs # Duplicate import, removed
from elevenlabs import play # For TTS playback
import threading
import queue
import traceback # Good for debugging
from datetime import datetime

# --- Load .env ---
load_dotenv()
AGENT_ID = os.getenv("AGENT_ID")
API_KEY = os.getenv("API_KEY")

# --- Thread-safe Message Queue ---
message_queue = queue.Queue()

# --- Initialize Session State ---
if "conversation_log" not in st.session_state:
    st.session_state.conversation_log = ""
    print("Initialized st.session_state.conversation_log")
if "conversation_active" not in st.session_state:
    st.session_state.conversation_active = False
    print("Initialized st.session_state.conversation_active")
if "conversation_object" not in st.session_state:
    st.session_state.conversation_object = None
if "tasks" not in st.session_state:
    st.session_state.tasks = []
if "selected_voice" not in st.session_state:
    # Default voice if not previously selected. Ensure this name exists in your voice_options.
    st.session_state.selected_voice = "Rachel" 
    print(f"Initialized st.session_state.selected_voice to {st.session_state.selected_voice}")

# --- Simulated Tool Functions ---
def get_calendar_events(date_str: str):
    print(f"[Tool Sim] Getting calendar for: {date_str}")
    return "Sales Meeting with Taipy at 10:00; Gym with Sophie at 17:00." if "today" in date_str.lower() else "No events found for that date."

def add_calendar_event(summary: str, start_time_str: str, end_time_str: str = None):
    print(f"[Tool Sim] Adding event: {summary} at {start_time_str}")
    return f"Event '{summary}' added at {start_time_str}. (Simulated)"

def search_web(query: str):
    print(f"[Tool Sim] Searching web for: {query}")
    return f"Simulated result: Search for '{query}' found relevant information."

def get_recipe(dish_name: str):
    print(f"[Tool Sim] Getting recipe for: {dish_name}")
    return f"Here's a simple recipe for {dish_name} (simulated ingredients and steps)."

def add_task(task_description: str):
    print(f"[Tool Sim] Adding task: {task_description}")
    if "tasks" not in st.session_state: # Ensure tasks list exists
        st.session_state.tasks = []
    st.session_state.tasks.append(task_description)
    return f"Task '{task_description}' added."

def get_tasks():
    print(f"[Tool Sim] Getting tasks.")
    if st.session_state.tasks:
        return "Your current tasks are: " + ", ".join(st.session_state.tasks)
    return "You have no tasks yet."

# --- Queue Callback Handlers ---
def queue_agent_response(text):
    print(f"Callback: Agent response (text): {text[:50]}...")
    message_queue.put(("agent", text))

def queue_user_transcript(text):
    print(f"Callback: User transcript: {text[:50]}...")
    message_queue.put(("user", text))

def queue_interrupted_response(original, corrected):
    print(f"Callback: Interrupted response, corrected: {corrected[:50]}...")
    message_queue.put(("interrupted", corrected))

# --- Conversation Thread ---
def run_conversation_session(conv_obj):
    print("CONV_THREAD: Conversation thread started.")
    try:
        conv_obj.start_session() # This is blocking and handles audio I/O
        print("CONV_THREAD: start_session() returned (session presumably ended cleanly).")
        message_queue.put(("ended", "Session ended by SDK."))
    except Exception as e:
        print(f"CONV_THREAD: An error occurred in start_session() or during conversation: {e}")
        print(f"CONV_THREAD: Traceback: {traceback.format_exc()}")
        message_queue.put(("error", str(e)))
    finally:
        # This ensures an 'ended' message is sent if start_session exits for any reason
        print("CONV_THREAD: Conversation thread finished execution block (finally).")
        message_queue.put(("ended_final", "Conversation thread processing finished."))

# --- ElevenLabs TTS Audio Playback ---
def speak_text(text_to_speak, voice_id_or_name="Rachel"): # Defaulted to Rachel
    """Plays the given text as speech using ElevenLabs TTS."""
    print(f"TTS: Attempting to speak: '{text_to_speak[:50]}...' with voice: {voice_id_or_name}")
    try:
        # Initialize client here to ensure it's fresh if API key changes or for thread safety
        # although for playback, it's usually fine.
        tts_client = ElevenLabs(api_key=API_KEY) 
        audio_stream = tts_client.generate(
            text=text_to_speak,
            voice=voice_id_or_name, # Can be a voice name, Voice object, or voice_id
            model="eleven_multilingual_v2" # Or your preferred model
        )
        print("TTS: Audio stream generated. Attempting to play...")
        play(audio_stream) # Plays the audio stream
        print("TTS: Playback finished.")
    except Exception as e:
        print(f"Error during TTS playback for text '{text_to_speak[:30]}...': {e}")
        # Optionally, put an error on the queue or display in Streamlit
        # message_queue.put(("tts_error", str(e)))


# --- UI ---
st.set_page_config(page_title="Voice Assistant", layout="centered") # Changed title slightly
st.title("🎙️ Your AI Voice Assistant")

user_name = st.text_input("Your Name", value=st.session_state.get("user_name_cache", "Alex"), key="user_name_input")
st.session_state.user_name_cache = user_name # Cache user name for reruns

schedule_input = st.text_area("Today's Schedule", value=st.session_state.get("schedule_cache", "Sales Meeting with Taipy at 10:00; Gym with Sophie at 17:00"), key="schedule_input")
st.session_state.schedule_cache = schedule_input # Cache schedule

# Voice selection - ensure this list matches voices available in your ElevenLabs account
# Or dynamically fetch them if preferred (adds a small delay on startup)
voice_options = ["Rachel", "Domi", "Bella", "Antoni", "Elli", "Adam", "Arnold"] # Example voices
try:
    current_voice_index = voice_options.index(st.session_state.selected_voice)
except ValueError:
    current_voice_index = 0 # Default to first voice if saved voice isn't in the list
    st.session_state.selected_voice = voice_options[current_voice_index]

st.session_state.selected_voice = st.selectbox(
    "Choose Voice Persona", 
    voice_options, 
    index=current_voice_index,
    key="voice_select"
)

# --- Start / Stop Buttons ---
col1, col2 = st.columns(2)
with col1:
    if st.button("▶️ Start Voice Assistant", disabled=st.session_state.get("conversation_active", False), key="start_conv_btn"):
        print("STREAMLIT_MAIN: 'Start Voice Assistant' button clicked.")
        if not AGENT_ID or not API_KEY:
            st.error("Missing AGENT_ID or API_KEY. Please set them in your .env file.")
        else:
            st.session_state.conversation_log = "Initializing conversation...\n" # Reset log
            st.session_state.conversation_active = True
            
            prompt = (
                f"You are a helpful and friendly personal assistant for {user_name}. "
                f"You manage tasks, your calendar, can search the web for information, and provide recipes. "
                f"Today's date is {datetime.now().strftime('%A, %B %d, %Y')}. "
                f"Your interlocutor, {user_name}, has the following schedule today: {schedule_input}. "
                f"Be proactive if appropriate, but always wait for the user to finish speaking."
            )
            first_message = f"Hello {user_name}! According to your schedule, you have: {schedule_input}. How can I help you today?"
            
            print(f"STREAMLIT_MAIN: Using prompt: {prompt[:100]}...")
            print(f"STREAMLIT_MAIN: Using first message: {first_message[:100]}...")

            conversation_override = {"agent": {"prompt": {"prompt": prompt}, "first_message": first_message}}
            
            # *** MODIFICATION HERE: Explicitly pass empty dicts for extra_body and dynamic_variables ***
            config = ConversationConfig(
                conversation_config_override=conversation_override,
                extra_body={},  # Ensure this attribute exists
                dynamic_variables={} # Ensure this attribute exists
            )
            # *** END MODIFICATION ***

            try:
                print("STREAMLIT_MAIN: Attempting to create ElevenLabs client and Conversation object.")
                client_instance = ElevenLabs(api_key=API_KEY) # Ensure client is instantiated for Conversation
                conversation = Conversation(
                    client_instance, 
                    AGENT_ID, 
                    config=config, 
                    requires_auth=True, # Usually true for agent interactions
                    audio_interface=DefaultAudioInterface(), # Uses system microphone and speakers
                    callback_agent_response=queue_agent_response,
                    callback_user_transcript=queue_user_transcript,
                    callback_agent_response_correction=queue_interrupted_response,
                )
                st.session_state.conversation_object = conversation
                print("STREAMLIT_MAIN: Conversation object created successfully.")
                
                thread = threading.Thread(target=run_conversation_session, args=(conversation,), daemon=True)
                thread.start()
                print(f"STREAMLIT_MAIN: Conversation thread '{thread.name}' started.")
                st.rerun() # Update UI to show "Stop" button and "Initializing..."
            except Exception as e:
                st.error(f"Failed to start conversation: {e}")
                print(f"STREAMLIT_MAIN: Exception during conversation setup: {e}\n{traceback.format_exc()}")
                st.session_state.conversation_active = False
                st.session_state.conversation_object = None
                st.session_state.conversation_log = f"Error starting conversation: {e}\n"
                # No st.rerun() here, error is already displayed.

with col2:
    if st.button("⏹️ Stop Voice Assistant", disabled=not st.session_state.get("conversation_active", False), key="stop_conv_btn"):
        print("STREAMLIT_MAIN: 'Stop Voice Assistant' button clicked.")
        if st.session_state.get("conversation_object"):
            try:
                print("STREAMLIT_MAIN: Calling conversation_object.end_session()")
                st.session_state.conversation_object.end_session()
                # The thread's 'finally' block should queue an 'ended_final' message.
                # We can add an immediate log update for responsiveness.
                st.session_state.conversation_log += "\nRequesting session end...\n"
                st.info("Stop request sent. Waiting for session to fully terminate.")
            except Exception as e:
                st.error(f"Error trying to stop session: {e}")
                print(f"STREAMLIT_MAIN: Exception calling end_session(): {e}")
        else:
            # If no conversation object, just ensure state is inactive
            print("STREAMLIT_MAIN: Stop button clicked, but no conversation object found. Setting inactive.")
        st.session_state.conversation_active = False # Force inactive state for UI
        st.rerun() # Update UI

# --- Manual Text Input as Fallback ---
st.markdown("--- \n ### 🧑 Manual Text Input (Fallback/Debug)")
user_text_input_val = st.text_input("Type here to simulate speaking to the assistant:", key="manual_text_input")
if st.button("Send Manual Text", key="send_manual_text_btn"):
    if user_text_input_val.strip():
        print(f"STREAMLIT_MAIN: Manual text input sent: '{user_text_input_val}'")
        # Simulate user speaking this text
        message_queue.put(("user", user_text_input_val.strip()))
        # Simulate an agent response (for testing UI update)
        # In a real scenario, this text would be processed by the agent if it could accept text input.
        # The current Conversation object is voice-centric.
        sim_response = f"I received your text: '{user_text_input_val.strip()}'. (This is a simulated text response)"
        message_queue.put(("agent", sim_response))
        st.rerun() # Update UI
    else:
        st.warning("Please enter some text to send.")

# --- Simulated Buttons for Tools (for UI testing) ---
st.markdown("### 🧪 Simulate Tool Interactions (for UI testing)")
if st.button("📅 Ask for today's calendar", key="sim_calendar_btn"):
    message_queue.put(("user", "What’s on my calendar today?"))
    message_queue.put(("agent", get_calendar_events("today")))
    st.rerun()

if st.button("🍝 Ask for pasta recipe", key="sim_recipe_btn"):
    message_queue.put(("user", "How do I make pasta?"))
    message_queue.put(("agent", get_recipe("pasta")))
    st.rerun()

if st.button("✅ Show tasks", key="sim_show_tasks_btn"):
    message_queue.put(("user", "What are my tasks?"))
    message_queue.put(("agent", get_tasks()))
    st.rerun()

# --- Process Queue and Update UI ---
rerun_ui_needed = False
processed_in_this_run = 0

if "conversation_log" not in st.session_state: # Ensure log exists
    st.session_state.conversation_log = ""

while not message_queue.empty():
    processed_in_this_run +=1
    try:
        msg_type, content = message_queue.get_nowait()
        print(f"STREAMLIT_MAIN: Dequeued message - Type: {msg_type}, Content: {str(content)[:60]}...")

        # Clear "Initializing..." once real content starts, unless it's an error replacing it
        if st.session_state.conversation_log == "Initializing conversation...\n" and msg_type != "error":
            st.session_state.conversation_log = ""
        
        if msg_type == "user":
            st.session_state.conversation_log += f"\n**🧑 You:** {content}\n"
        elif msg_type == "agent":
            st.session_state.conversation_log += f"\n**🤖 Assistant:** {content}\n"
            # Speak the assistant's response in a separate thread to avoid blocking UI
            tts_thread = threading.Thread(target=speak_text, args=(content, st.session_state.selected_voice), daemon=True)
            tts_thread.start()
        elif msg_type == "interrupted":
            st.session_state.conversation_log += f"\n**(🤖 Assistant - interrupted, corrected):** {content}\n"
            tts_thread = threading.Thread(target=speak_text, args=(content, st.session_state.selected_voice), daemon=True)
            tts_thread.start()
        elif msg_type.startswith("ended"): # Catches "ended" and "ended_final"
            print(f"STREAMLIT_MAIN: Processing '{msg_type}' status. Content: {content}")
            if st.session_state.conversation_active: # Only log "ended" once if still marked active
                st.session_state.conversation_log += f"\n[{content}]\n"
            st.session_state.conversation_active = False # Ensure inactive
            st.session_state.conversation_object = None
        elif msg_type == "error":
            error_log_message = f"\n**Error:** {content}\n"
            if st.session_state.conversation_log == "Initializing conversation...\n":
                 st.session_state.conversation_log = error_log_message
            else:
                st.session_state.conversation_log += error_log_message
            st.session_state.conversation_active = False # Stop on error
            st.session_state.conversation_object = None
        
        rerun_ui_needed = True
    except queue.Empty:
        # This should not be reached if `while not message_queue.empty()` is used,
        # but it's a safe break.
        print("STREAMLIT_MAIN: Queue became empty during processing loop.")
        break
    except Exception as e:
        print(f"STREAMLIT_MAIN: Error processing message queue item: {e}\n{traceback.format_exc()}")
        st.session_state.conversation_log += f"\n[System Error in Queue Processing: {e}]\n"
        rerun_ui_needed = True # Rerun to show this system error

if processed_in_this_run > 0:
    print(f"STREAMLIT_MAIN: Processed {processed_in_this_run} messages from queue in this run.")
    print(f"STREAMLIT_MAIN: Current conversation_log snippet: '{st.session_state.conversation_log[-100:]}'")


# --- Log Display ---
st.markdown("--- \n ### 📜 Conversation Log")
# Use a container for the log display that can be updated
log_display_area = st.empty() 

current_log_for_display = st.session_state.get("conversation_log", "")
if not current_log_for_display.strip():
    log_display_area.markdown("_Conversation will appear here once started._")
elif current_log_for_display == "Initializing conversation...\n":
    log_display_area.markdown("Initializing conversation...")
else:
    # Using markdown directly within the placeholder
    log_display_area.markdown(
        f"<div style='height:300px;overflow-y:auto;padding:10px;border:1px solid #ccc;background-color:#f9f9f9;white-space:pre-wrap;font-family:monospace;'>{current_log_for_display}</div>", 
        unsafe_allow_html=True
    )
print(f"STREAMLIT_MAIN: Displaying log. Full content for UI (first 200 chars): '{current_log_for_display[:200]}'")


# --- Save Log Button ---
if st.button("💾 Save Log to File", key="save_log_btn"):
    if st.session_state.conversation_log.strip() and st.session_state.conversation_log != "Initializing conversation...\n":
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"conversation_log_{timestamp}.txt"
            with open(filename, "w", encoding="utf-8") as f:
                # Write a cleaner version without the markdown for plain text log
                clean_log = st.session_state.conversation_log.replace("**🧑 You:**", "You:")
                clean_log = clean_log.replace("**🤖 Assistant:**", "Assistant:")
                clean_log = clean_log.replace("**(🤖 Assistant - interrupted, corrected):**", "Assistant (interrupted):")
                f.write(clean_log.strip())
            st.success(f"Conversation log saved as {filename}")
            print(f"STREAMLIT_MAIN: Log saved to {filename}")
        except Exception as e:
            st.error(f"Failed to save log: {e}")
            print(f"STREAMLIT_MAIN: Error saving log: {e}")
    else:
        st.warning("No conversation to save yet.")

# If UI needs a rerun due to queue processing, do it now.
if rerun_ui_needed:
    print("STREAMLIT_MAIN: Calling st.rerun() at the end of script due to processed messages.")
    st.rerun()

print(f"STREAMLIT_MAIN: End of script run. Conversation Active: {st.session_state.conversation_active}")
