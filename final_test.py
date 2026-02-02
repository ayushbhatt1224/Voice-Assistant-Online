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
from thefuzz import process, fuzz 

# --- 1. DATABASE & INITIALIZATION ---
DB_NAME = 'foodchain_pro.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS menu 
                      (item_name TEXT PRIMARY KEY, price REAL, emoji TEXT, upsell_item TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS nlu_dataset 
                      (text_query TEXT, intent TEXT, item TEXT, qty INTEGER)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS customers 
                      (customer_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, phone TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS orders 
                      (order_id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER,
                       timestamp TEXT, items TEXT, total_price REAL,
                       FOREIGN KEY(customer_id) REFERENCES customers(customer_id))''')
    conn.commit(); conn.close()

init_db()

# --- 2. DYNAMIC LOADERS ---
def load_menu():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM menu", conn)
    conn.close()
    df = df[df['item_name'].notna() & (df['item_name'] != "") & df['price'].notna()]
    return {row['item_name'].lower(): {"price": row['price'], "img": row['emoji'], "upsell": row['upsell_item']} for _, row in df.iterrows()}

def get_best_match(user_item, menu_list):
    if not user_item or not menu_list: return None
    clean_item = re.sub(r'(s|es)$', '', user_item.lower().strip())
    match, score = process.extractOne(clean_item, menu_list, scorer=fuzz.token_set_ratio)
    return match if score > 55 else None

def speak_text(text):
    try:
        pipeline = KPipeline(lang_code='a')
        for _, _, audio in pipeline(text, voice='af_heart', speed=1.1): sd.play(audio, 24000)
        sd.wait(); del pipeline; gc.collect()
    except: pass

st.set_page_config(page_title="Giggs Pro Assistant", page_icon="🎙️", layout="wide")

# --- 3. THE REFINED ENGINE ---
def hybrid_process(user_text):
    text_clean = re.sub(r'[^a-zA-Z0-9\s]', '', user_text.lower().strip())
    current_menu = load_menu()
    menu_items = list(current_menu.keys())
    
    # PRIORITY 1: MENU QUERY
    if any(word in text_clean for word in ["menu", "items", "list", "options"]):
        items_str = ", ".join([f"{i.title()} (₹{current_menu[i]['price']})" for i in menu_items])
        return f"Certainly! We have: {items_str}. What would you like?"

    # PRIORITY 2: CHECKOUT STATE MACHINE
    if st.session_state.checkout_step == "GET_NAME":
        st.session_state.temp_name = user_text; st.session_state.checkout_step = "GET_PHONE"
        return f"Thank you, {user_text}. And your phone number?"
    if st.session_state.checkout_step == "GET_PHONE":
        st.session_state.temp_phone = user_text; st.session_state.trigger_final_save = True
        return "Saving your details now. Thank you!"

    # PRIORITY 3: CHECKOUT TRIGGER
    if any(word in text_clean for word in ["confirm", "checkout", "done", "bill"]):
        if not st.session_state.cart: return "Your cart is empty!"
        st.session_state.checkout_step = "GET_NAME"
        return "Great! What is your full name?"

    # --- PRIORITY 4: PRECISION SCANNER (FIXED INTENT DETECTION) ---
    feedback = []
    num_map = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "ek": 1, "do": 2}
    
    # Split segments by connectors
    segments = re.split(r'\band\b|,|\bplus\b|\binstead\b', text_clean)
    
    for seg in segments:
        seg = seg.strip()
        if not seg: continue
        
        qty = 1
        digits = re.findall(r'\d+', seg)
        if digits: qty = int(digits[0])
        else:
            for word, val in num_map.items():
                if word in seg: qty = val; break
        
        item = get_best_match(seg, menu_items)
        if item:
            # Check for removal intent specifically in this segment or right before it
            is_removal = any(x in seg for x in ["remove", "delete", "hatao", "dont", "no", "minus", "hata"])
            
            if is_removal:
                if item in st.session_state.cart:
                    st.session_state.cart[item] = max(0, st.session_state.cart[item] - qty)
                    if st.session_state.cart[item] == 0: del st.session_state.cart[item]
                    feedback.append(f"removed {qty} {item}")
                else:
                    feedback.append(f"no {item} in cart")
            else:
                st.session_state.cart[item] = st.session_state.cart.get(item, 0) + qty
                feedback.append(f"added {qty} {item}")

    if feedback:
        return f"Done! I've updated your order: {', '.join(feedback)}. Anything else?"
    
    return "I only understand menu items. Try 'Add a burger' or 'Remove the cake'."

# --- 4. VOICE INTERACTION ---
def run_assistant():
    if not st.session_state.has_greeted:
        welcome_msg = "Welcome to FoodChain AI! I am Giggs. How can I help you today?"
        st.session_state.messages.append({"role": "assistant", "content": welcome_msg})
        st.session_state.has_greeted = True
        speak_text(welcome_msg); return

    p = pyaudio.PyAudio(); RATE, CHUNK = 16000, 1024
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=RATE, input=True, frames_per_buffer=CHUNK)
    with st.status("🎙️ Listening...") as status:
        frames = [stream.read(CHUNK) for _ in range(0, int(RATE / CHUNK * 5))]
    stream.stop_stream(); stream.close(); p.terminate()
    
    with wave.open("input.wav", 'wb') as wf:
        wf.setnchannels(1); wf.setsampwidth(p.get_sample_size(pyaudio.paInt16)); wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))

    stt_model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, _ = stt_model.transcribe("input.wav")
    user_text = "".join([s.text for s in segments]).strip()
    
    if user_text:
        st.session_state.messages.append({"role": "user", "content": user_text})
        reply = hybrid_process(user_text)
        if not st.session_state.get('clear_ui_now'):
            st.session_state.messages.append({"role": "assistant", "content": reply})
            speak_text(reply)
        else:
            speak_text(reply); st.session_state.clear_ui_now = False; st.rerun()

# --- 5. UI ---
if "cart" not in st.session_state: st.session_state.cart = {}
if "messages" not in st.session_state: st.session_state.messages = []
if "checkout_step" not in st.session_state: st.session_state.checkout_step = "IDLE"
if "has_greeted" not in st.session_state: st.session_state.has_greeted = False

with st.sidebar:
    st.title("🎙️ Menu")
    m = load_menu()
    for item, info in m.items(): st.write(f"{info['img']} **{item.title()}** - ₹{info['price']}")

st.header("🎙️ Giggs Commercial Kiosk")
t1, t2, t3, t4 = st.tabs(["🛒 Kiosk", "📊 Sales History", "⚙️ Menu Manager", "📚 AI Knowledge"])

with t1:
    col1, col2 = st.columns([2, 1])
    with col1:
        if st.button("🎙️ TAP TO SPEAK", use_container_width=True, type="primary"): run_assistant(); st.rerun()
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]): st.markdown(msg["content"])
    with col2:
        st.subheader("🛒 Cart")
        m = load_menu(); total = sum(m[itm]['price'] * q for itm, q in st.session_state.cart.items())
        for itm, q in st.session_state.cart.items(): st.write(f"**{q}x {itm.title()}** - ₹{m[itm]['price']*q}")
        st.divider(); st.metric("Total Bill", f"₹{total}")
        
        if st.session_state.get('trigger_final_save'):
            conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
            cursor.execute("INSERT INTO customers (name, phone) VALUES (?, ?)", (st.session_state.temp_name, st.session_state.temp_phone))
            cust_id = cursor.lastrowid
            cursor.execute("INSERT INTO orders (customer_id, timestamp, items, total_price) VALUES (?, ?, ?, ?)", 
                           (cust_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), json.dumps(st.session_state.cart), total))
            conn.commit(); conn.close()
            st.success("Order Logged!"); st.session_state.cart = {}; st.session_state.messages = []
            st.session_state.checkout_step = "IDLE"; st.session_state.has_greeted = False
            st.session_state.trigger_final_save = False; st.rerun()

with t2:
    st.header("Analytics")
    try:
        conn = sqlite3.connect(DB_NAME)
        query = "SELECT customers.name, orders.timestamp, orders.items, orders.total_price FROM orders JOIN customers ON orders.customer_id = customers.customer_id"
        df = pd.read_sql_query(query, conn); conn.close(); st.dataframe(df, use_container_width=True)
    except: st.info("No data.")

with t3:
    st.header("Menu Manager")
    conn = sqlite3.connect(DB_NAME); df = pd.read_sql_query("SELECT * FROM menu", conn)
    edited = st.data_editor(df, num_rows="dynamic", key="menu_editor")
    if st.button("Save Menu"): edited.to_sql("menu", conn, if_exists="replace", index=False); st.rerun()
    conn.close()

with t4:
    st.header("AI Knowledge")
    conn = sqlite3.connect(DB_NAME); df = pd.read_sql_query("SELECT * FROM nlu_dataset", conn)
    edited_nlu = st.data_editor(df, num_rows="dynamic", key="nlu_editor")
    if st.button("Update"): edited_nlu.to_sql("nlu_dataset", conn, if_exists="replace", index=False); st.rerun()
    conn.close()