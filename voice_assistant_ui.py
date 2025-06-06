import streamlit as st
import os
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from elevenlabs.conversational_ai.conversation import Conversation
from elevenlabs.conversational_ai.default_audio_interface import DefaultAudioInterface
from elevenlabs.types import ConversationConfig, Voice # Added Voice for type hinting
from elevenlabs import play, stream # For TTS playback
import threading
import queue
import traceback # Good for debugging
from datetime import datetime
import random # For jokes

# --- Load .env ---
load_dotenv()
AGENT_ID = os.getenv("AGENT_ID")
API_KEY = os.getenv("API_KEY")

# --- Thread-safe Message Queue ---
message_queue = queue.Queue()

# --- Initialize Session State ---
# Helper function to initialize state if not present
def init_session_state(key, value, print_msg=True):
    if key not in st.session_state:
        st.session_state[key] = value
        if print_msg:
            print(f"Initialized st.session_state.{key}")

init_session_state("conversation_log_structured", []) # Store as list of dicts: {"role": "user/assistant", "content": "message"}
init_session_state("conversation_active", False)
init_session_state("conversation_object", None)
init_session_state("tasks", [])
init_session_state("selected_voice_id", None) # Store voice ID for TTS
init_session_state("user_name_cache", "Alex")
init_session_state("schedule_cache", "Sales Meeting with Taipy at 10:00; Gym with Sophie at 17:00")
init_session_state("assistant_is_thinking", False)


# --- ElevenLabs Client & Voices ---
try:
    eleven_client = ElevenLabs(api_key=API_KEY)
    available_voices = eleven_client.voices.get_all().voices
    voice_options_map = {v.name: v.voice_id for v in available_voices if v.name and v.voice_id}
    if not voice_options_map:
        st.error("No voices found or failed to load voices from ElevenLabs. Check API key and account.")
        st.stop()
    if st.session_state.selected_voice_id not in voice_options_map.values():
        st.session_state.selected_voice_id = next(iter(voice_options_map.values())) 
        print(f"Defaulted selected_voice_id to {st.session_state.selected_voice_id}")
except Exception as e:
    st.error(f"Error initializing ElevenLabs client or fetching voices: {e}")
    print(f"Fatal error initializing ElevenLabs: {e}\n{traceback.format_exc()}")
    st.stop()


# --- Simulated Tool Functions ---
def get_calendar_events(date_str: str):
    print(f"[Tool Sim] Getting calendar for: {date_str}")
    return "Based on your schedule: Sales Meeting with Taipy at 10:00; Gym with Sophie at 17:00." if "today" in date_str.lower() else "I couldn't find any events for that date."

def add_calendar_event(summary: str, start_time_str: str, end_time_str: str = None):
    print(f"[Tool Sim] Adding event: {summary} at {start_time_str}")
    return f"Okay, I've (simulated) adding '{summary}' to your calendar at {start_time_str}."

def search_web(query: str):
    print(f"[Tool Sim] Searching web for: {query}")
    return f"I've (simulated) searching the web for '{query}' and found some interesting results."

def get_recipe(dish_name: str):
    print(f"[Tool Sim] Getting recipe for: {dish_name}")
    return f"Sure! Here's a (simulated) delicious recipe for {dish_name}: combine ingredients and cook well!"

def add_task(task_description: str):
    print(f"[Tool Sim] Adding task: {task_description}")
    if "tasks" not in st.session_state: st.session_state.tasks = []
    st.session_state.tasks.append(task_description)
    return f"Got it! I've (simulated) adding task: '{task_description}'."

def get_tasks():
    print(f"[Tool Sim] Getting tasks.")
    if st.session_state.tasks:
        return "Your current tasks are: " + ", ".join(st.session_state.tasks)
    return "You don't have any tasks on your list right now."

JOKES = [
    "Why don't scientists trust atoms? Because they make up everything!",
    "Why did the scarecrow win an award? Because he was outstanding in his field!",
    "Why don't skeletons fight each other? They don't have the guts."
]
def get_joke(): return random.choice(JOKES)
def get_current_time(): return f"The current time is {datetime.now().strftime('%I:%M %p, %A, %B %d')}."

# --- Queue Callback Handlers ---
def queue_agent_response(text):
    print(f"Callback: Agent response (text): {text[:50]}...")
    message_queue.put(("agent_text", text))

def queue_user_transcript(text):
    print(f"Callback: User transcript: {text[:50]}...")
    message_queue.put(("user_text", text))
    message_queue.put(("assistant_thinking", True))

def queue_interrupted_response(original, corrected):
    print(f"Callback: Interrupted response, corrected: {corrected[:50]}...")
    message_queue.put(("interrupted_text", corrected))

# --- Conversation Thread ---
def run_conversation_session(conv_obj):
    print("CONV_THREAD: Conversation thread started.")
    try:
        conv_obj.start_session() 
        print("CONV_THREAD: start_session() returned.")
        message_queue.put(("ended", "Session ended by SDK."))
    except Exception as e:
        print(f"CONV_THREAD: Error: {e}\n{traceback.format_exc()}")
        message_queue.put(("error", str(e)))
    finally:
        print("CONV_THREAD: Finished.")
        message_queue.put(("ended_final", "Thread processing finished."))
        message_queue.put(("assistant_thinking", False))

# --- ElevenLabs TTS Audio Playback ---
def speak_text_threaded(text_to_speak, voice_id_to_use):
    print(f"TTS_THREAD: Speaking: '{text_to_speak[:50]}...' with voice ID: {voice_id_to_use}")
    try:
        audio_stream = eleven_client.generate(text=text_to_speak, voice=voice_id_to_use, model="eleven_multilingual_v2")
        print("TTS_THREAD: Audio stream generated. Playing...")
        play(audio_stream) 
        print("TTS_THREAD: Playback finished.")
    except Exception as e:
        print(f"TTS Error for '{text_to_speak[:30]}...': {e}")
        message_queue.put(("error", f"TTS Error: {e}")) 

# --- UI ---
st.set_page_config(page_title="AI Voice Assistant", layout="wide") 
st.title("🎙️ Your Enhanced AI Voice Assistant ✨")

with st.sidebar:
    st.header("⚙️ Assistant Settings")
    user_name = st.text_input("Your Name", value=st.session_state.user_name_cache, key="user_name_sidebar_input")
    st.session_state.user_name_cache = user_name
    schedule_input = st.text_area("Today's Schedule", value=st.session_state.schedule_cache, height=100, key="schedule_sidebar_input")
    st.session_state.schedule_cache = schedule_input
    voice_display_names = list(voice_options_map.keys())
    try:
        default_voice_name = next(name for name, v_id in voice_options_map.items() if v_id == st.session_state.selected_voice_id)
        current_voice_index = voice_display_names.index(default_voice_name)
    except (StopIteration, ValueError):
        current_voice_index = 0 
        if voice_display_names: st.session_state.selected_voice_id = voice_options_map[voice_display_names[current_voice_index]]
        else: st.warning("No voices available.")
    selected_voice_name_display = st.selectbox("Choose Voice Persona", voice_display_names, index=current_voice_index, key="voice_select_sidebar", disabled=not voice_display_names)
    if voice_display_names and voice_options_map.get(selected_voice_name_display) != st.session_state.selected_voice_id:
        st.session_state.selected_voice_id = voice_options_map[selected_voice_name_display]
        print(f"Sidebar: Voice changed to {selected_voice_name_display} (ID: {st.session_state.selected_voice_id})")
        st.rerun()
    st.markdown("---")
    if st.button("🗑️ Clear Chat History", key="clear_chat_btn"):
        st.session_state.conversation_log_structured = []
        st.session_state.tasks = [] 
        print("UI: Chat history cleared.")
        st.rerun()

main_col1, main_col2 = st.columns([2,1]) 
with main_col1:
    st.markdown("### 📜 Conversation Log")
    log_for_render_debug = st.session_state.get("conversation_log_structured", [])
    print(f"UI_RENDER: About to render chat_container with {len(log_for_render_debug)} messages. First message content (if any): {log_for_render_debug[0]['content'] if log_for_render_debug else 'N/A'}")
    chat_container = st.container(height=400) 
    with chat_container:
        for msg in log_for_render_debug: 
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
        if st.session_state.get("assistant_is_thinking", False):
            with st.chat_message("assistant"):
                st.markdown("🤖 _Assistant is thinking..._")

with main_col2:
    st.markdown("### 🎤 Controls & Actions")
    if st.button("▶️ Start Voice Assistant", disabled=st.session_state.get("conversation_active", False), use_container_width=True, key="start_conv_main_btn"):
        print("STREAMLIT_MAIN: 'Start Voice Assistant' button clicked.")
        if not AGENT_ID or not API_KEY: st.error("Missing AGENT_ID or API_KEY.")
        else:
            st.session_state.conversation_log_structured = [{"role": "assistant", "content": "Initializing conversation..."}]
            st.session_state.conversation_active = True
            current_time_for_prompt = datetime.now().strftime('%A, %B %d, %Y, %I:%M %p')
            prompt = (
                f"You are an advanced, friendly, and slightly witty personal assistant for {st.session_state.user_name_cache}. "
                f"Your primary functions include: managing tasks, checking the calendar, searching the web for information, providing recipes, telling jokes, and stating the current time. "
                f"Today's date and time is {current_time_for_prompt}. "
                f"Your interlocutor, {st.session_state.user_name_cache}, has the following schedule today: {st.session_state.schedule_cache}. "
                f"Engage naturally, be proactive if it makes sense, but always wait for the user to finish speaking before responding."
            )
            first_message = f"Hi {st.session_state.user_name_cache}! It's {current_time_for_prompt}. Your schedule shows: {st.session_state.schedule_cache}. What can I do for you?"
            print(f"STREAMLIT_MAIN: Using prompt: {prompt[:100]}...")
            print(f"STREAMLIT_MAIN: Using first message: {first_message[:100]}...")
            conversation_override = {"agent": {"prompt": {"prompt": prompt}, "first_message": first_message}}
            config = ConversationConfig(conversation_config_override=conversation_override, extra_body={}, dynamic_variables={})
            try:
                print("STREAMLIT_MAIN: Attempting to create Conversation object.")
                conversation = Conversation(eleven_client, AGENT_ID, config=config, requires_auth=True, audio_interface=DefaultAudioInterface(), callback_agent_response=queue_agent_response, callback_user_transcript=queue_user_transcript, callback_agent_response_correction=queue_interrupted_response)
                st.session_state.conversation_object = conversation
                print("STREAMLIT_MAIN: Conversation object created successfully.")
                thread = threading.Thread(target=run_conversation_session, args=(conversation,), daemon=True)
                thread.start()
                print(f"STREAMLIT_MAIN: Conversation thread '{thread.name}' started.")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to start conversation: {e}")
                print(f"STREAMLIT_MAIN: Exception during conversation setup: {e}\n{traceback.format_exc()}")
                st.session_state.conversation_active = False
                st.session_state.conversation_object = None
                message_queue.put(("error", f"Init Error: {e}")) 
                st.rerun()

    if st.button("⏹️ Stop Voice Assistant", disabled=not st.session_state.get("conversation_active", False), use_container_width=True, key="stop_conv_main_btn"):
        print("STREAMLIT_MAIN: 'Stop Voice Assistant' button clicked.")
        if st.session_state.get("conversation_object"):
            try:
                print("STREAMLIT_MAIN: Calling conversation_object.end_session()")
                st.session_state.conversation_object.end_session()
                message_queue.put(("user_action", "Stop request sent. Waiting for session to terminate..."))
            except Exception as e: st.error(f"Error trying to stop session: {e}"); print(f"STREAMLIT_MAIN: Exception calling end_session(): {e}")
        st.session_state.conversation_active = False 
        st.session_state.assistant_is_thinking = False
        st.rerun()
    st.markdown("---"); st.markdown("##### Quick Actions:")
    if st.button("🕰️ What's the time?", use_container_width=True, key="time_btn"): message_queue.put(("user_text", "What's the time?")); message_queue.put(("assistant_thinking", True)); message_queue.put(("agent_text", get_current_time())) 
    if st.button("😄 Tell me a joke!", use_container_width=True, key="joke_btn"): message_queue.put(("user_text", "Tell me a joke!")); message_queue.put(("assistant_thinking", True)); message_queue.put(("agent_text", get_joke())) 
    st.markdown("---")
    if st.button("💾 Save Full Log", key="save_log_main_btn"):
        if st.session_state.conversation_log_structured:
            try:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S'); filename = f"full_conversation_log_{timestamp}.txt"; log_content_to_save = ""
                for msg in st.session_state.conversation_log_structured: prefix = "You: " if msg["role"] == "user" else "Assistant: "; log_content_to_save += prefix + msg["content"] + "\n"
                with open(filename, "w", encoding="utf-8") as f: f.write(log_content_to_save.strip())
                st.success(f"Full conversation log saved as {filename}"); print(f"STREAMLIT_MAIN: Log saved to {filename}")
            except Exception as e: st.error(f"Failed to save log: {e}"); print(f"STREAMLIT_MAIN: Error saving log: {e}")
        else: st.warning("No conversation to save yet.")

rerun_ui_needed_flag = False 
processed_messages_this_run = 0
while not message_queue.empty():
    processed_messages_this_run += 1
    try:
        msg_type, content = message_queue.get_nowait()
        print(f"STREAMLIT_MAIN: Dequeued message - Type: {msg_type}, Content: {str(content)[:60]}...")
        
        # MODIFIED LOGIC for handling "Initializing..."
        is_initializing = (len(st.session_state.conversation_log_structured) == 1 and 
                           st.session_state.conversation_log_structured[0].get("content") == "Initializing conversation...")

        new_message_entry = None
        if msg_type == "user_text":
            new_message_entry = {"role": "user", "content": content}
        elif msg_type == "agent_text":
            st.session_state.assistant_is_thinking = False 
            new_message_entry = {"role": "assistant", "content": content}
            if st.session_state.selected_voice_id: 
                tts_thread = threading.Thread(target=speak_text_threaded, args=(content, st.session_state.selected_voice_id), daemon=True); tts_thread.start()
            else: print("TTS_THREAD: No voice selected for TTS.")
        elif msg_type == "interrupted_text":
            st.session_state.assistant_is_thinking = False
            new_message_entry = {"role": "assistant", "content": f"(Interrupted, corrected): {content}"}
            if st.session_state.selected_voice_id:
                tts_thread = threading.Thread(target=speak_text_threaded, args=(content, st.session_state.selected_voice_id), daemon=True); tts_thread.start()
        elif msg_type == "assistant_thinking":
            st.session_state.assistant_is_thinking = content 
        elif msg_type.startswith("ended"): 
            print(f"STREAMLIT_MAIN: Processing '{msg_type}' status. Content: {content}")
            if st.session_state.conversation_active: 
                new_message_entry = {"role": "assistant", "content": f"[{content}]"}
            st.session_state.conversation_active = False 
            st.session_state.conversation_object = None
            st.session_state.assistant_is_thinking = False
        elif msg_type == "error":
            error_message = f"Error: {content}"
            new_message_entry = {"role": "assistant", "content": error_message}
            st.session_state.conversation_active = False 
            st.session_state.conversation_object = None
            st.session_state.assistant_is_thinking = False
        elif msg_type == "user_action": 
            new_message_entry = {"role": "assistant", "content": f"[{content}]"}
        
        if new_message_entry:
            if is_initializing and msg_type not in ["error", "ended", "ended_final"]: # Replace "Initializing..."
                st.session_state.conversation_log_structured = [new_message_entry]
            else: # Append to existing or new log
                st.session_state.conversation_log_structured.append(new_message_entry)
        
        rerun_ui_needed_flag = True
    except queue.Empty: print("STREAMLIT_MAIN: Queue became empty."); break
    except Exception as e:
        print(f"STREAMLIT_MAIN: Error processing queue: {e}\n{traceback.format_exc()}")
        st.session_state.conversation_log_structured.append({"role":"assistant", "content": f"[System Error in Queue: {e}]"})
        rerun_ui_needed_flag = True

if processed_messages_this_run > 0: print(f"STREAMLIT_MAIN: Processed {processed_messages_this_run} messages.")
if rerun_ui_needed_flag: print("STREAMLIT_MAIN: Calling st.rerun()."); st.rerun()

print(f"STREAMLIT_MAIN: End of script run. Active: {st.session_state.conversation_active}, Thinking: {st.session_state.assistant_is_thinking}")
