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

# Mapping for words to numbers (English & Hindi)
NUM_MAP = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, 
    "ek": 1, "do": 2, "teen": 3, "char": 4, "panch": 5
}

st.set_page_config(page_title="FoodChain AI Pro", page_icon="🍔", layout="wide")

# --- 2. PERFORMANCE HELPERS ---
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
    except: pass

# --- 3. THE HYBRID LOGIC ---
def process_logic_and_get_reply(text):
    text_lower = text.lower()
    
    # --- STEP 1: EXTRACT QUANTITY ---
    qty = 1
    # Look for digits (3)
    digits = re.findall(r'\d+', text_lower)
    if digits:
        qty = int(digits[0])
    else:
        # Look for words (three/teen)
        for word, val in NUM_MAP.items():
            if word in text_lower:
                qty = val
                break

    # --- STEP 2: DETECT INTENT (ADD VS REMOVE) ---
    is_removal = any(word in text_lower for word in ["remove", "cancel", "hatao", "nahin", "nhi", "delete"])
    
    # --- STEP 3: UPDATE CART ---
    items_updated = []
    for item in MENU_LIST:
        # Check if any keyword of the menu item is in the text
        keywords = item.split()
        if any(k in text_lower for k in keywords):
            if is_removal:
                if item in st.session_state.cart:
                    st.session_state.cart[item] = max(0, st.session_state.cart[item] - qty)
                    if st.session_state.cart[item] == 0: del st.session_state.cart[item]
                    items_updated.append(f"removed {qty} {item}")
            else:
                st.session_state.cart[item] = st.session_state.cart.get(item, 0) + qty
                items_updated.append(f"added {qty} {item}")

    # --- STEP 4: GENERATE AI CONVERSATION ---
    current_cart = ", ".join([f"{q} {i}" for i, q in st.session_state.cart.items()]) if st.session_state.cart else "empty"
    
    prompt = f"""
    Context: You are a FoodChain cashier. 
    Action taken: {', '.join(items_updated) if items_updated else 'No items matched'}.
    User said: "{text}".
    Cart now: {current_cart}.
    Rule: Confirm the change naturally. Max 12 words. NEVER ask about toppings or sizes.
    """
    
    try:
        res = ollama.chat(model='qwen2.5:0.5b', messages=[{'role': 'system', 'content': prompt}])
        reply = res['message']['content']
        # Fail-safe: if AI halluicates a question, replace it
        if "?" in reply and "else" not in reply.lower():
            return f"Understood. I've updated your cart. Anything else?"
        return reply
    except:
        return "Cart updated. What's next?"

# --- 4. INTERACTION LOOP ---
def run_assistant():
    CHUNK, RATE = 1024, 16000
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=RATE, input=True)
    with st.spinner("🎙️ Listening..."):
        frames = [stream.read(CHUNK) for _ in range(0, int(RATE / CHUNK * 6))]
    stream.stop_stream(); stream.close(); p.terminate()
    
    with wave.open("input.wav", 'wb') as wf:
        wf.setnchannels(1); wf.setsampwidth(p.get_sample_size(pyaudio.paInt16)); wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))

    stt_model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, info = stt_model.transcribe("input.wav", beam_size=3)
    user_text = "".join([s.text for s in segments]).strip()
    del stt_model
    clear_ram()
    
    if user_text:
        st.session_state.messages.append({"role": "user", "content": user_text})
        
        # Determine Welcome vs Normal
        if not st.session_state.session_active:
            st.session_state.session_active = True
            welcome = "Welcome to FoodChain! "
            reply = process_logic_and_get_reply(user_text)
            full_reply = welcome + reply
        else:
            full_reply = process_logic_and_get_reply(user_text)

        st.session_state.messages.append({"role": "assistant", "content": full_reply})
        speak_text(full_reply, lang='hi' if info.language == 'hi' else 'en')

# --- 5. UI ---
if "cart" not in st.session_state: st.session_state.cart = {}
if "messages" not in st.session_state: st.session_state.messages = []
if "session_active" not in st.session_state: st.session_state.session_active = False

tab_order, tab_manager = st.tabs(["🛒 Take Order", "📊 Dashboard"])

with tab_order:
    st.title("🍔 FoodChain AI Pro V2")
    c1, c2 = st.columns([2, 1])
    with c1:
        label = "🚀 START CONVERSATION" if not st.session_state.session_active else "🎙️ TAP TO SPEAK"
        if st.button(label, use_container_width=True, type="primary"):
            run_assistant(); st.rerun()
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]): st.markdown(msg["content"])
    with c2:
        st.subheader("🛒 Cart")
        total = sum(MENU[itm] * q for itm, q in st.session_state.cart.items())
        for itm, q in st.session_state.cart.items():
            st.write(f"**{q}x {itm.title()}** - ₹{MENU[itm]*q}")
        st.divider(); st.markdown(f"### Total: ₹{total}")
        if st.button("✅ CONFIRM & SAVE", use_container_width=True):
            if st.session_state.cart:
                conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
                cursor.execute("INSERT INTO orders (timestamp, items, total_price) VALUES (?, ?, ?)",
                    (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), json.dumps(st.session_state.cart), total))
                conn.commit(); conn.close()
                speak_text(f"Thank you! Total is {total} rupees.")
                st.session_state.cart = {}; st.session_state.messages = []; st.session_state.session_active = False
                st.rerun()