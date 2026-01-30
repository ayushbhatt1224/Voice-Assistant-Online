import streamlit as st
import ollama
from faster_whisper import WhisperModel
from kokoro import KPipeline
import sounddevice as sd
import pyaudio
import wave
import json
import sqlite3
import pandas as pd
import re
import gc 
from datetime import datetime

# --- 1. SETTINGS & MENU ---
DB_NAME = 'foodchain_orders.db'
MENU = {
    "classic burger": 150, "cheese pizza": 299, "masala chai": 40,
    "cold coffee": 60, "peri peri fries": 90, "paneer samosa": 20, "coke": 50
}
MENU_LIST = list(MENU.keys())
NUM_MAP = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "ek": 1, "do": 2, "teen": 3}

st.set_page_config(page_title="FoodChain POS Pro", page_icon="🍔", layout="wide")

# --- 2. HELPERS ---
def clear_ram():
    gc.collect()

def speak_text(text, lang='en'):
    try:
        pipeline = KPipeline(lang_code='a' if lang == 'en' else 'h')
        gen = pipeline(text, voice='af_heart', speed=1.1)
        for _, _, audio in gen:
            sd.play(audio, 24000)
        sd.wait() 
        del pipeline
        clear_ram()
    except Exception as e:
        st.error(f"Audio Error: {e}")

# --- 3. RESOURCE LOADING ---
def get_stt():
    return WhisperModel("base", device="cpu", compute_type="int8")

# --- 4. LOGIC ---
def process_voice_intent(text):
    text_lower = text.lower()
    if any(word in text_lower for word in ["total", "bill", "price", "amount"]):
        current_total = sum(MENU[itm] * q for itm, q in st.session_state.cart.items())
        return f"Your total is {current_total} rupees."

    qty_found = re.findall(r'\d+', text_lower)
    quantity = int(qty_found[0]) if qty_found else 1
    if not qty_found:
        for word, val in NUM_MAP.items():
            if word in text_lower:
                quantity = val
                break

    is_removal = any(word in text_lower for word in ["remove", "cancel", "hatao", "nahin"])
    items_modified = []
    for official_name in MENU_LIST:
        keywords = official_name.split()
        if any(word in text_lower for word in keywords):
            if is_removal:
                if official_name in st.session_state.cart:
                    st.session_state.cart[official_name] = max(0, st.session_state.cart[official_name] - quantity)
                    if st.session_state.cart[official_name] == 0: del st.session_state.cart[official_name]
                    items_modified.append(f"removed {quantity} {official_name}")
            else:
                st.session_state.cart[official_name] = st.session_state.cart.get(official_name, 0) + quantity
                items_modified.append(f"added {quantity} {official_name}")
            
    if items_modified: return f"Done. {', '.join(items_modified)}."
    return "I heard you, but I didn't catch a menu item."

# --- 5. INTERACTION ---
def run_assistant():
    CHUNK, RATE = 1024, 16000
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=RATE, input=True)
    with st.spinner("🎙️ Listening..."):
        frames = [stream.read(CHUNK) for _ in range(0, int(RATE / CHUNK * 5))]
    stream.stop_stream(); stream.close(); p.terminate()
    
    with wave.open("input.wav", 'wb') as wf:
        wf.setnchannels(1); wf.setsampwidth(p.get_sample_size(pyaudio.paInt16)); wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))

    stt_model = get_stt()
    segments, info = stt_model.transcribe("input.wav", beam_size=3)
    user_text = "".join([s.text for s in segments]).strip()
    del stt_model
    clear_ram()
    
    if user_text:
        st.session_state.messages.append({"role": "user", "content": user_text})
        reply = process_voice_intent(user_text)
        st.session_state.messages.append({"role": "assistant", "content": reply})
        speak_text(reply, lang='hi' if info.language == 'hi' else 'en')

# --- 6. UI & SESSION LOGIC ---
if "cart" not in st.session_state: st.session_state.cart = {}
if "messages" not in st.session_state: st.session_state.messages = []
if "session_active" not in st.session_state: st.session_state.session_active = False

tab_order, tab_manager = st.tabs(["🛒 Take Order", "📊 Manager Dashboard"])

with tab_order:
    st.title("🍔 FoodChain POS")
    c1, c2 = st.columns([2, 1])
    
    with c1:
        # SWITCHING BUTTON LOGIC
        if not st.session_state.session_active:
            if st.button("🚀 START CONVERSATION", use_container_width=True, type="secondary"):
                welcome_msg = "Welcome to FoodChain! How can I help you today?"
                st.session_state.messages.append({"role": "assistant", "content": welcome_msg})
                st.session_state.session_active = True
                speak_text(welcome_msg)
                st.rerun()
        else:
            if st.button("🎙️ TAP TO SPEAK", use_container_width=True, type="primary"):
                run_assistant()
                st.rerun()
        
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]): 
                st.markdown(msg["content"])

    with c2:
        st.subheader("🛒 Current Cart")
        total = sum(MENU[itm] * q for itm, q in st.session_state.cart.items())
        for itm, q in st.session_state.cart.items():
            st.write(f"**{q}x {itm.title()}** - ₹{MENU[itm]*q}")
        
        st.divider()
        st.markdown(f"### Total: ₹{total}")
        
        if st.button("✅ CONFIRM & SAVE", type="primary", use_container_width=True):
            if st.session_state.cart:
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                cursor.execute("INSERT INTO orders (timestamp, items, total_price) VALUES (?, ?, ?)",
                    (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), json.dumps(st.session_state.cart), total))
                conn.commit(); conn.close()

                exit_msg = f"Order saved. Your total is {total} rupees. Thank you!"
                speak_text(exit_msg)

                # Reset all states for the next user
                st.session_state.cart = {}
                st.session_state.messages = []
                st.session_state.session_active = False 
                st.rerun()

with tab_manager:
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM orders ORDER BY id DESC", conn)
    conn.close()
    if not df.empty:
        st.metric("Total Sales", f"₹{df['total_price'].sum()}")
        st.dataframe(df, use_container_width=True)