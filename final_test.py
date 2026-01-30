import streamlit as st
import ollama
from faster_whisper import WhisperModel
from kokoro import KPipeline
import sounddevice as sd
import pyaudio
import wave
import json
import sqlite3
import pandas as pd  # FIXED: Corrected the import here
import re
import gc 
from datetime import datetime

# --- 1. SETTINGS & RELATIONAL DATABASE ---
DB_NAME = 'foodchain_pro.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Table 1: Customers
    cursor.execute('''CREATE TABLE IF NOT EXISTS customers 
                      (customer_id INTEGER PRIMARY KEY AUTOINCREMENT, 
                       name TEXT, 
                       phone TEXT)''')
    # Table 2: Orders (Linked via Foreign Key)
    cursor.execute('''CREATE TABLE IF NOT EXISTS orders 
                      (order_id INTEGER PRIMARY KEY AUTOINCREMENT, 
                       customer_id INTEGER,
                       timestamp TEXT, 
                       items TEXT, 
                       total_price REAL,
                       FOREIGN KEY(customer_id) REFERENCES customers(customer_id))''')
    conn.commit()
    conn.close()

init_db()

MENU = {
    "classic burger": {"price": 150, "img": "🍔", "upsell": "coke"},
    "cheese pizza": {"price": 299, "img": "🍕", "upsell": "peri peri fries"},
    "masala chai": {"price": 40, "img": "☕", "upsell": "paneer samosa"},
    "cold coffee": {"price": 60, "img": "🥤", "upsell": "classic burger"},
    "peri peri fries": {"price": 90, "img": "🍟", "upsell": "coke"},
    "paneer samosa": {"price": 20, "img": "🥟", "upsell": "masala chai"},
    "coke": {"price": 50, "img": "🥤", "upsell": "peri peri fries"}
}
MENU_LIST = list(MENU.keys())
NUM_MAP = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "ek": 1, "do": 2, "teen": 3}

st.set_page_config(page_title="Giggs Voice Assistant", page_icon="🎙️", layout="wide")

# --- 2. THE SMART HYBRID ENGINE ---
def hybrid_process(user_text):
    # Strip punctuation for cleaner matching
    text_clean = re.sub(r'[^a-zA-Z0-9\s]', '', user_text.lower().strip())
    
    # --- ROUTE 1: THE GREETING WALL (Highest Priority) ---
    greetings = ["hello", "hi", "hey", "morning", "how are you", "namaste", "helo"]
    if any(g in text_clean for g in greetings) and len(text_clean.split()) < 5:
        return "Good morning! I am Giggs Voice Assistant. I am doing great! What would you like to order today?"

    # --- ROUTE 2: EMPTY CART EXIT ---
    negative_intents = ["no", "nothing", "stop", "dont want", "cancel", "bye", "exit"]
    if not st.session_state.cart and any(neg in text_clean for neg in negative_intents):
        st.session_state.messages = [] # Clear chat
        return "No problem at all! Giggs Voice Assistant is resetting. Have a wonderful day!"

    # --- ROUTE 3: SEQUENTIAL CHECKOUT (Relational DB Flow) ---
    if st.session_state.checkout_step == "GET_NAME":
        st.session_state.temp_name = user_text
        st.session_state.checkout_step = "GET_PHONE"
        return f"Thank you, {user_text}. And what is your phone number?"

    if st.session_state.checkout_step == "GET_PHONE":
        st.session_state.temp_phone = user_text
        st.session_state.trigger_final_save = True
        return "Perfect. Giggs Assistant is saving your details and generating your final bill now."

    if any(word in text_clean for word in ["checkout", "done", "finished", "bill", "i am done"]):
        if not st.session_state.cart:
            return "Your cart is currently empty! Would you like to see the menu or should I close this session?"
        st.session_state.checkout_step = "GET_NAME"
        return "Excellent! To finalize your receipt, please tell me your full name."

    # --- ROUTE 4: ORDER LOGIC (Multi-Action Scanner) ---
    items_changed = []
    suggested_item = None
    parts = re.split(r'\band\b|\bbut\b|\binstead\b|,', text_clean)
    
    for part in parts:
        part = part.strip()
        local_qty = 1
        nums = re.findall(r'\d+', part)
        if nums: local_qty = int(nums[0])
        else:
            for word, val in NUM_MAP.items():
                if word in part: local_qty = val; break
        
        is_removal = any(word in part for word in ["remove", "cancel", "delete", "no"])
        for item in MENU_LIST:
            if any(word in part for word in item.split()):
                if is_removal:
                    if item in st.session_state.cart:
                        st.session_state.cart[item] = max(0, st.session_state.cart[item] - local_qty)
                        if st.session_state.cart[item] == 0: del st.session_state.cart[item]
                        items_changed.append(f"removed {local_qty} {item}")
                else:
                    st.session_state.cart[item] = st.session_state.cart.get(item, 0) + local_qty
                    items_changed.append(f"added {local_qty} {item}")
                    suggested_item = MENU[item]['upsell']

    # --- ROUTE 5: AI CONFIRMATION ---
    if items_changed:
        report = " and ".join(items_changed)
        upsell = f" Would you like to add {suggested_item}?" if suggested_item else ""
        prompt = f"Role: Giggs Voice Assistant. Confirm ONLY {report}. Then ask: {upsell} Max 12 words."
        try:
            res = ollama.chat(model='qwen2.5:0.5b', messages=[{'role': 'system', 'content': prompt}])
            return res['message']['content'].replace("$", "₹")
        except:
            return f"Updated! I've {report}. {upsell}"
    
    return "Giggs Assistant heard you, but I didn't catch an order. Try asking 'What is on the menu?'"

# --- 3. INTERACTION ---
def run_assistant():
    p = pyaudio.PyAudio()
    RATE, CHUNK = 16000, 1024
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=RATE, input=True, frames_per_buffer=CHUNK)
    with st.status("🎙️ **Giggs Assistant Listening...**") as status:
        frames = [stream.read(CHUNK) for _ in range(0, int(RATE / CHUNK * 5))]
        status.update(label="⚙️ **Processing Voice...**", state="running")
    stream.stop_stream(); stream.close()
    with wave.open("input.wav", 'wb') as wf:
        wf.setnchannels(1); wf.setsampwidth(p.get_sample_size(pyaudio.paInt16)); wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))
    p.terminate()

    stt_model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, _ = stt_model.transcribe("input.wav")
    user_text = "".join([s.text for s in segments]).strip()
    
    if user_text:
        st.session_state.messages.append({"role": "user", "content": user_text})
        reply = hybrid_process(user_text)
        st.session_state.messages.append({"role": "assistant", "content": reply})
        try:
            pipeline = KPipeline(lang_code='a')
            for _, _, audio in pipeline(reply, voice='af_heart', speed=1.1): sd.play(audio, 24000)
            sd.wait(); del pipeline; gc.collect()
        except: pass

# --- 4. MAIN UI ---
if "cart" not in st.session_state: st.session_state.cart = {}
if "messages" not in st.session_state: st.session_state.messages = []
if "checkout_step" not in st.session_state: st.session_state.checkout_step = "IDLE"
if "temp_name" not in st.session_state: st.session_state.temp_name = ""
if "temp_phone" not in st.session_state: st.session_state.temp_phone = ""
if "trigger_final_save" not in st.session_state: st.session_state.trigger_final_save = False

with st.sidebar:
    st.title("🎙️ Giggs Menu")
    for item, info in MENU.items():
        st.write(f"{info['img']} **{item.title()}** - ₹{info['price']}")

st.header("🎙️ Giggs Voice Assistant Terminal")

t1, t2 = st.tabs(["🛒 Kiosk", "📊 Relational Database"])

with t1:
    col1, col2 = st.columns([2, 1])
    with col1:
        if st.button("🎙️ TAP TO SPEAK", use_container_width=True, type="primary"):
            run_assistant(); st.rerun()
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]): st.markdown(msg["content"])
    with col2:
        st.subheader("📋 Order Summary")
        total = sum(MENU[itm]['price'] * q for itm, q in st.session_state.cart.items())
        for itm, q in st.session_state.cart.items():
            st.write(f"**{q}x {itm.title()}** - ₹{MENU[itm]['price']*q}")
        st.divider(); st.metric("Total Bill", f"₹{total}")

        if st.session_state.trigger_final_save:
            conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
            # Insert Customer Details
            cursor.execute("INSERT INTO customers (name, phone) VALUES (?, ?)", 
                           (st.session_state.temp_name, st.session_state.temp_phone))
            cust_id = cursor.lastrowid
            # Insert Order Linked to Customer
            cursor.execute("INSERT INTO orders (customer_id, timestamp, items, total_price) VALUES (?, ?, ?, ?)",
                (cust_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), json.dumps(st.session_state.cart), total))
            conn.commit(); conn.close()
            st.success(f"✅ Saved for {st.session_state.temp_name}!")
            st.session_state.cart = {}; st.session_state.messages = []
            st.session_state.checkout_step = "IDLE"; st.session_state.trigger_final_save = False
            st.balloons(); st.rerun()

with t2:
    st.header("Admin: Relational Sales Data")
    try:
        conn = sqlite3.connect(DB_NAME)
        # Professional SQL Join to show off your M.Tech skills
        query = '''SELECT customers.name, customers.phone, orders.timestamp, orders.items, orders.total_price 
                   FROM orders JOIN customers ON orders.customer_id = customers.customer_id'''
        df = pd.read_sql_query(query, conn)
        conn.close()
        st.dataframe(df, use_container_width=True)
    except: st.info("No data yet.")