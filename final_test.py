import streamlit as st
from groq import Groq
from streamlit_mic_recorder import mic_recorder
import pandas as pd
import sqlite3
import io
import re
import base64
import time
from thefuzz import process, fuzz
from gtts import gTTS

# --- 1. UI & AUTO-STOP ---
st.set_page_config(page_title="Giggs FoodChain", layout="wide")

st.markdown("""
    <script>
    // Auto-stop recording after 4 seconds to keep it snappy
    const observer = new MutationObserver((mutations) => {
        const buttons = document.querySelectorAll('button');
        buttons.forEach(btn => {
            if (btn.innerText.includes("⏹️ STOP & PROCESS")) {
                setTimeout(() => { btn.click(); }, 4000); 
            }
        });
    });
    observer.observe(document.body, { childList: true, subtree: true });
    </script>
    <style>
    .stApp { background-color: #0e1117; color: white; }
    #MainMenu, footer, header {visibility: hidden;}
    .stButton > button {
        width: 100%; height: 60px; font-weight: bold;
        background-color: #ffc72c !important; color: #da291c !important;
        border-radius: 10px; border: 2px solid #da291c;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. INITIALIZATION ---
DB_NAME = 'foodchain_pro.db'
if "cart" not in st.session_state: st.session_state.cart = {}
if "messages" not in st.session_state: st.session_state.messages = []
if "recorder_id" not in st.session_state: st.session_state.recorder_id = 0
if "first_interaction" not in st.session_state: st.session_state.first_interaction = True

client = Groq(api_key=st.secrets["GROQ_API_KEY"])

def load_menu():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM menu", conn)
    conn.close()
    return {row['item_name'].lower(): row['price'] for _, row in df.iterrows()}

def process_order_precision(user_text):
    text_clean = re.sub(r'[^a-zA-Z0-9\s]', ' ', user_text.lower().strip())
    menu_data = load_menu()
    menu_items = list(menu_data.keys())
    
    if any(word in text_clean for word in ["menu", "list", "items", "what is"]):
        return f"We have {', '.join([i.title() for i in menu_items])}. What can I get for you?"

    feedback = []
    num_map = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
    chunks = re.split(r'\band\b|,|\bplus\b|\binstead\b', text_clean)
    
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk: continue
        qty = 1
        found_num = re.findall(r'\d+', chunk)
        if found_num: qty = int(found_num[0])
        else:
            for word, val in num_map.items():
                if word in chunk: qty = val; break
        
        match, score = process.extractOne(chunk, menu_items, scorer=fuzz.token_set_ratio)
        if match and score > 50:
            is_removal = any(x in chunk for x in ["remove", "delete", "hatao", "no"])
            if is_removal:
                if match in st.session_state.cart:
                    st.session_state.cart[match] = max(0, st.session_state.cart[match] - qty)
                    if st.session_state.cart[match] <= 0: del st.session_state.cart[match]
                    feedback.append(f"removed {qty} {match}")
            else:
                st.session_state.cart[match] = st.session_state.cart.get(match, 0) + qty
                feedback.append(f"added {qty} {match}")
    return f"Done! I've {', '.join(feedback)}." if feedback else "I can help with your order!"

# --- 3. UI LAYOUT ---
st.title("🍔 Giggs Digital Kiosk")

with st.expander("🛡️ Staff Admin Portal"):
    conn = sqlite3.connect(DB_NAME)
    df_menu = pd.read_sql_query("SELECT * FROM menu", conn)
    edited_df = st.data_editor(df_menu, num_rows="dynamic", key="menu_editor")
    if st.button("Save Changes"):
        edited_df.to_sql("menu", conn, if_exists="replace", index=False)
        st.rerun()
    conn.close()

col1, col2 = st.columns([2, 1])

with col1:
    audio_data = mic_recorder(
        start_prompt="🔴 TAP TO START ORDERING", 
        stop_prompt="⏹️ STOP & PROCESS", 
        key=f"mic_{st.session_state.recorder_id}"
    )
    
    if audio_data:
        if st.session_state.first_interaction:
            st.session_state.first_interaction = False
            reply_text = "Hello! Welcome to Giggs FoodChain. How can I help you today?"
            st.session_state.messages.append({"role": "assistant", "content": reply_text})
        else:
            audio_bio = io.BytesIO(audio_data['bytes']); audio_bio.name = "audio.wav"
            user_text = client.audio.transcriptions.create(file=audio_bio, model="whisper-large-v3", response_format="text")
            reply_text = process_order_precision(user_text)
            st.session_state.messages.append({"role": "user", "content": user_text})
            st.session_state.messages.append({"role": "assistant", "content": reply_text})

        # --- NATIVE AUDIO PLAYBACK ---
        tts = gTTS(text=reply_text, lang='en', tld='co.uk')
        audio_fp = io.BytesIO()
        tts.write_to_fp(audio_fp)
        
        # We display the audio player. By setting autoplay=True, 
        # it will play as soon as it renders.
        st.audio(audio_fp, format="audio/mp3", autoplay=True)
        
        # Update recorder_id so the NEXT tap uses a fresh microphone instance
        st.session_state.recorder_id += 1
        # No immediate st.rerun here! This allows the audio to play fully.

    # Display Chat
    for m in st.session_state.messages:
        with st.chat_message(m["role"]): st.write(m["content"])

with col2:
    st.header("🛒 Your Tray")
    menu_data = load_menu()
    total = sum(menu_data.get(itm, 0) * q for itm, q in st.session_state.cart.items())
    for itm, q in st.session_state.cart.items():
        st.write(f"**{q}x {itm.title()}** - ₹{menu_data.get(itm, 0) * q}")
    st.divider(); st.metric("Total Bill", f"₹{total}")
    if st.button("🚀 COMPLETE ORDER"):
        st.balloons(); st.session_state.cart = {}; st.session_state.messages = []; st.session_state.first_interaction = True; st.rerun()