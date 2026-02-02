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

st.set_page_config(page_title="FoodChain Pro", page_icon="🍔", layout="wide")

# --- 2. HELPERS ---
def clear_ram():
    gc.collect()

def speak_text(text, lang='en'):
    try:
        pipeline = KPipeline(lang_code='a' if lang == 'en' else 'h')
        gen = pipeline(text, voice='af_heart', speed=1.1)
        for _, _, audio in gen: sd.play(audio, 24000)
        sd.wait(); del pipeline; clear_ram()
    except: pass

# --- 3. THE "BOUNCER" LOGIC ENGINE ---
def hybrid_process(user_text):
    text_lower = user_text.lower().strip()
    
    # --- ROUTE 1: GREETINGS (Hard Bypass - AI is turned OFF here) ---
    greetings = ["hello", "hi", "how are you", "hey", "good morning", "morning"]
    if any(text_lower.startswith(g) for g in greetings) and len(text_lower.split()) < 5:
        return "Hello! I am doing great. Welcome to FoodChain! What can I get for you today?"

    # --- ROUTE 2: MENU QUERY (Hard Bypass - AI is turned OFF here) ---
    menu_keywords = ["menu", "items", "list", "have", "sell", "card", "options"]
    if any(m in text_lower for m in menu_keywords):
        items_str = ", ".join([f"{item.title()} (₹{price})" for item, price in MENU.items()])
        return f"We have: {items_str}. What would you like to order?"

    # --- ROUTE 3: ORDER LOGIC (Python Math) ---
    qty = 1
    nums = re.findall(r'\d+', text_lower)
    if nums: qty = int(nums[0])
    else:
        for word, val in NUM_MAP.items():
            if word in text_lower: qty = val; break

    is_removal = any(word in text_lower for word in ["remove", "cancel", "hatao", "nahin", "delete", "no"])
    
    items_changed = []
    for item in MENU_LIST:
        if any(word in text_lower.split() for word in item.split()):
            if is_removal:
                if item in st.session_state.cart:
                    st.session_state.cart[item] = max(0, st.session_state.cart[item] - qty)
                    if st.session_state.cart[item] == 0: del st.session_state.cart[item]
                    items_changed.append(f"REMOVED {qty} {item}")
            else:
                st.session_state.cart[item] = st.session_state.cart.get(item, 0) + qty
                items_changed.append(f"ADDED {qty} {item}")

    # --- ROUTE 4: ORDER CONFIRMATION (AI ONLY USED HERE) ---
    if items_changed:
        report = ", ".join(items_changed)
        current_cart = ", ".join([f"{q} {i}" for i, q in st.session_state.cart.items()])
        
        prompt = f"Cashier: Confirm {report}. Total cart: {current_cart}. Max 10 words. No sizes/toppings."
        try:
            # We only wake up Ollama if there is an actual order change to talk about
            res = ollama.chat(model='qwen2.5:0.5b', messages=[{'role': 'user', 'content': prompt}])
            return res['message']['content']
        except:
            return f"Done! I've {report}. Anything else?"
    
    # --- ROUTE 5: FALLBACK ---
    return "I heard you, but I didn't catch a menu item. You can ask for burgers, pizza, or chai."

# --- 4. INTERACTION ---
def run_assistant():
    CHUNK, RATE = 1024, 16000
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=RATE, input=True)
    
    # LIVE MIC ICON (Adding the requested status indicator)
    with st.status("🔴 **LIVE MIC: LISTENING...**", expanded=True) as status:
        frames = [stream.read(CHUNK) for _ in range(0, int(RATE / CHUNK * 6))]
        status.update(label="🟢 **PROCESSING VOICE...**", state="running")
    
    stream.stop_stream(); stream.close(); p.terminate()
    
    with wave.open("input.wav", 'wb') as wf:
        wf.setnchannels(1); wf.setsampwidth(p.get_sample_size(pyaudio.paInt16)); wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))

    stt_model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, _ = stt_model.transcribe("input.wav", beam_size=3)
    user_text = "".join([s.text for s in segments]).strip()
    del stt_model
    clear_ram()
    
    if user_text:
        st.session_state.messages.append({"role": "user", "content": user_text})
        reply = hybrid_process(user_text)
        st.session_state.messages.append({"role": "assistant", "content": reply})
        speak_text(reply)

# --- 5. UI ---
if "cart" not in st.session_state: st.session_state.cart = {}
if "messages" not in st.session_state: st.session_state.messages = []

st.title("🍔 FoodChain Hybrid AI Pro")
c1, c2 = st.columns([2, 1])

with c1:
    if st.button("🎙️ TAP TO SPEAK", use_container_width=True, type="primary"):
        run_assistant(); st.rerun()
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])

with c2:
    st.subheader("🛒 Current Cart")
    total = sum(MENU[itm] * q for itm, q in st.session_state.cart.items())
    for itm, q in st.session_state.cart.items():
        st.write(f"**{q}x {itm.title()}** - ₹{MENU[itm]*q}")
    st.divider(); st.markdown(f"### Total: ₹{total}")
    if st.button("✅ CONFIRM ORDER", use_container_width=True):
        if st.session_state.cart:
            conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
            cursor.execute("INSERT INTO orders (timestamp, items, total_price) VALUES (?, ?, ?)",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), json.dumps(st.session_state.cart), total))
            conn.commit(); conn.close()
            speak_text(f"Thank you! Your order is saved.")
            st.session_state.cart = {}; st.session_state.messages = []; st.rerun()