import streamlit as st
import os
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from elevenlabs.conversational_ai.conversation import Conversation
from elevenlabs.types import ConversationConfig
import threading
import queue
import traceback
from streamlit_audio_recorder import audio_recorder

# Load environment variables
load_dotenv()
AGENT_ID = os.getenv("AGENT_ID")
API_KEY = os.getenv("API_KEY")

message_queue = queue.Queue()

if "conversation_log" not in st.session_state:
    st.session_state.conversation_log = ""
if "conversation_object" not in st.session_state:
    st.session_state.conversation_object = None
if "conversation_active" not in st.session_state:
    st.session_state.conversation_active = False

def queue_agent_response(text):
    message_queue.put(("agent", text))

def queue_user_transcript(text):
    message_queue.put(("user_transcript", text))

def run_conversation_listener(conv_obj):
    try:
        conv_obj.start_session()
        message_queue.put(("ended", "Session ended."))
    except Exception as e:
        message_queue.put(("error", str(e)))
    finally:
        message_queue.put(("ended_from_finally", "Session thread finished."))

# --- UI ---
st.set_page_config(page_title="AI Voice Assistant")
st.title("🎤 Real-Time AI Voice Assistant")

user_name = st.text_input("Your Name", "Alex")

col1, col2 = st.columns(2)
with col1:
    if st.button("Start Voice Assistant", disabled=st.session_state.conversation_active):
        st.session_state.conversation_log = "Initializing...\n"
        st.session_state.conversation_active = True

        prompt = "You're a helpful personal AI assistant for scheduling and task reminders."

        config = ConversationConfig(
            conversation_config_override={
                "agent": {
                    "prompt": {"prompt": prompt},
                    "first_message": f"Hello {user_name}, how can I assist you today?"
                }
            }
        )

        client = ElevenLabs(api_key=API_KEY)
        conversation = Conversation(
            client,
            agent_id=AGENT_ID,
            config=config,
            requires_auth=True,
            callback_agent_response=queue_agent_response,
            callback_user_transcript=queue_user_transcript,
        )
        st.session_state.conversation_object = conversation

        thread = threading.Thread(target=run_conversation_listener, args=(conversation,))
        thread.start()
        st.rerun()

with col2:
    if st.button("Stop Voice Assistant", disabled=not st.session_state.conversation_active):
        if st.session_state.conversation_object:
            try:
                st.session_state.conversation_object.end_session()
            except:
                pass
        st.session_state.conversation_active = False
        st.rerun()

if st.session_state.conversation_active:
    st.subheader("🎙️ Speak now")
    audio_bytes = audio_recorder(
        text="Click to Record", 
        sample_rate=16000, 
        pause_threshold=1.5, 
        icon_size="2x", 
        key="recorder"
    )

    if audio_bytes:
        try:
            conversation = st.session_state.get("conversation_object")
            if conversation:
                conversation.stream(audio_bytes)  # ✅ Correct method to send audio
                message_queue.put(("user_audio", f"(Audio sent: {len(audio_bytes)} bytes)"))
                st.rerun()
        except Exception as e:
            st.error(f"Failed to send audio: {e}")
            message_queue.put(("error", str(e)))

# --- Process message queue ---
while not message_queue.empty():
    msg_type, content = message_queue.get_nowait()
    if msg_type == "agent":
        st.session_state.conversation_log += f"\n**Assistant:** {content}"
    elif msg_type == "user_transcript":
        st.session_state.conversation_log += f"\n**You (transcript):** {content}"
    elif msg_type == "user_audio":
        st.session_state.conversation_log += f"\n**You:** {content}"
    elif msg_type in ["ended", "ended_from_finally"]:
        st.session_state.conversation_active = False
    elif msg_type == "error":
        st.error(f"Error: {content}")
        st.session_state.conversation_active = False

# --- Show conversation log ---
st.markdown("---")
st.subheader("📝 Conversation Log")
log_text = st.session_state.get("conversation_log", "").strip()
if log_text:
    st.markdown(f"<div style='overflow-y:scroll; height:300px; padding:10px; border:1px solid #ccc; white-space:pre-wrap;'>{log_text}</div>", unsafe_allow_html=True)
else:
    st.info("Start a conversation to see the log.")
