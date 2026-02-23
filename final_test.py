import streamlit as st
from groq import Groq
from streamlit_mic_recorder import mic_recorder
import pandas as pd
import sqlite3
import io
import re
import json
import time
from thefuzz import process, fuzz
from gtts import gTTS
from datetime import datetime

# --- 1. UI & AUTO-STOP SCRIPT ---
st.set_page_config(page_title="Giggs FoodChain", layout="wide")

st.markdown("""
    <script>
    const observer = new MutationObserver((mutations) => {
        const buttons = document.querySelectorAll('button');
        buttons.forEach(btn => {
            if (btn.innerText.includes("⏹️ PROCESSING...")) {
                setTimeout(() => { btn.click(); }, 3000); 
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

# --- 2. DATABASE & INITIALIZATION ---
DB_NAME = 'foodchain_pro.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT customer_id FROM orders LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("DROP TABLE IF EXISTS orders")
        cursor.execute("DROP TABLE IF EXISTS customers")

    cursor.execute('CREATE TABLE IF NOT EXISTS menu (item_name TEXT PRIMARY KEY, price REAL)')
    cursor.execute('''CREATE TABLE IF NOT EXISTS customers 
                      (customer_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, phone TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS orders 
                      (order_id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER,
                       timestamp TEXT, items TEXT, total_price REAL,
                       FOREIGN KEY(customer_id) REFERENCES customers(customer_id))''')
    conn.commit()
    conn.close()

init_db()

# Ensure ALL keys exist to prevent AttributeErrors
keys = {
    "cart": {}, "messages": [], "recorder_id": 0, 
    "first_interaction": True, "checkout_step": "IDLE", 
    "temp_name": "", "temp_phone": "", "trigger_final_save": False
}
for key, value in keys.items():
    if key not in st.session_state:
        st.session_state[key] = value

client = Groq(api_key=st.secrets["GROQ_API_KEY"])

def load_menu():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM menu", conn)
    conn.close()
    return {row['item_name'].lower(): float(row['price']) if row['price'] else 0.0 for _, row in df.iterrows()}

def process_order_precision(user_text):
    user_text = str(user_text)
    text_clean = user_text.lower().strip()
    
    exit_phrases = ["i don't want to order anything", "i dont want to order anything", "cancel everything", "exit", "close", "stop"]
    clear_phrases = ["clear my cart", "empty the tray", "reset order", "sab hata do", "empty my cart"]

    if any(phrase in text_clean for phrase in exit_phrases):
        return "RESET_SESSION"

    if any(phrase in text_clean for phrase in clear_phrases):
        st.session_state.cart = {}
        st.session_state.checkout_step = "IDLE"
        return "Understood. I've cleared your tray. What else would you like to add?"

    if st.session_state.checkout_step == "GET_NAME":
        st.session_state.temp_name = user_text
        st.session_state.checkout_step = "GET_PHONE"
        return f"Thank you, {user_text}. Can I have your phone number?"
    
    if st.session_state.checkout_step == "GET_PHONE":
        phone_digits = "".join(re.findall(r'\d+', user_text))
        st.session_state.temp_phone = phone_digits
        st.session_state.trigger_final_save = True
        return "Got it. Saving your order now. Thank you!"

    menu_data = load_menu()
    menu_items = list(menu_data.keys())
    if any(word in text_clean for word in ["menu", "list", "items", "what is"]):
        if not menu_items: return "The menu is currently empty."
        return f"We have {', '.join([i.title() for i in menu_items])}. What can I get you?"

    if any(word in text_clean for word in ["confirm", "checkout", "done", "bill"]):
        if not st.session_state.cart: return "Your tray is empty!"
        st.session_state.checkout_step = "GET_NAME"
        return "Perfect. What is your full name?"

    feedback = []
    num_map = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
    text_clean_processed = re.sub(r'[^a-zA-Z0-9\s]', ' ', text_clean)
    chunks = re.split(r'\band\b|,|\bplus\b|\binstead\b', text_clean_processed)
    
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk or len(chunk) < 2: continue 
        qty = 1
        found_num = re.findall(r'\d+', chunk)
        if found_num: qty = int(found_num[0])
        else:
            for word, val in num_map.items():
                if word in chunk: qty = val; break
        
        match_result = process.extractOne(chunk, menu_items, scorer=fuzz.partial_ratio)
        if match_result and match_result[1] > 60:
            match = match_result[0]
            if any(x in chunk for x in ["remove", "delete", "no", "minus"]):
                if match in st.session_state.cart:
                    st.session_state.cart[match] = max(0, st.session_state.cart[match] - qty)
                    if st.session_state.cart[match] <= 0: del st.session_state.cart[match]
                    feedback.append(f"removed {match}")
            else:
                st.session_state.cart[match] = st.session_state.cart.get(match, 0) + qty
                feedback.append(f"added {qty} {match}")
                    
    return f"Sure! I've {', '.join(feedback)}." if feedback else "I didn't quite catch that. Could you repeat?"

# --- 3. UI LAYOUT ---
st.title("🍔 Giggs Digital Kiosk")

with st.expander("🛡️ Staff Admin Portal"):
    t1, t2 = st.tabs(["📝 Menu Manager", "📊 Sales History"])
    conn = sqlite3.connect(DB_NAME)
    with t1:
        df_menu = pd.read_sql_query("SELECT * FROM menu", conn)
        edited_df = st.data_editor(df_menu, num_rows="dynamic", key="menu_editor")
        if st.button("Save Changes"):
            edited_df.to_sql("menu", conn, if_exists="replace", index=False)
            st.rerun()
    with t2:
        try:
            query = "SELECT customers.name, orders.timestamp, orders.items, orders.total_price FROM orders JOIN customers ON orders.customer_id = customers.customer_id ORDER BY orders.order_id DESC"
            df_sales = pd.read_sql_query(query, conn)
            st.dataframe(df_sales, use_container_width=True)
        except: st.info("No orders yet.")
    conn.close()

col1, col2 = st.columns([2, 1])

with col1:
    audio_data = mic_recorder(
        start_prompt="🔴 TAP ONCE TO SPEAK", 
        stop_prompt="⏹️ PROCESSING...", 
        key=f"mic_{st.session_state.recorder_id}"
    )
    
    if audio_data:
        audio_bio = io.BytesIO(audio_data['bytes'])
        audio_bio.name = "audio.wav" 
        user_text = client.audio.transcriptions.create(file=audio_bio, model="whisper-large-v3", response_format="text")
        
        if st.session_state.first_interaction:
            st.session_state.first_interaction = False
            reply_text = "Hello! Welcome to Giggs FoodChain. What can I get for you today?"
        else:
            reply_text = process_order_precision(user_text)

        if reply_text == "RESET_SESSION":
            goodbye = "No problem! Starting a fresh session. Goodbye!"
            tts = gTTS(text=goodbye, lang='en', tld='co.uk')
            audio_fp = io.BytesIO(); tts.write_to_fp(audio_fp)
            st.audio(audio_fp, format="audio/mp3", autoplay=True)
            time.sleep(4) 
            st.session_state.clear()
            st.rerun()

        st.session_state.messages.append({"role": "user", "content": user_text})
        st.session_state.messages.append({"role": "assistant", "content": reply_text})

        # VOICE OUTPUT
        tts = gTTS(text=reply_text, lang='en', tld='co.uk')
        audio_fp = io.BytesIO(); tts.write_to_fp(audio_fp)
        st.audio(audio_fp, format="audio/mp3", autoplay=True)
        
        # NATIVE DYNAMIC REFRESH
        # Calculate speaking time (approx 15 chars per second) + 2s safety buffer
        speak_time = (len(reply_text) / 15) + 2
        
        # Increment ID so the mic is fresh on refresh
        st.session_state.recorder_id += 1
        
        # Wait for audio to play, then refresh automatically
        time.sleep(speak_time) 
        st.rerun()

    for m in st.session_state.messages:
        with st.chat_message(m["role"]): st.write(m["content"])

with col2:
    st.header("🛒 Your Tray")
    menu_data = load_menu()
    total = sum(float(menu_data.get(itm, 0)) * int(q) for itm, q in st.session_state.cart.items())
    for itm, q in st.session_state.cart.items():
        st.write(f"**{q}x {itm.title()}** - ₹{float(menu_data.get(itm, 0)) * q}")
    st.divider(); st.metric("Total Bill", f"₹{total}")
    
    if st.session_state.trigger_final_save:
        conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
        cursor.execute("INSERT INTO customers (name, phone) VALUES (?, ?)", (st.session_state.temp_name, st.session_state.temp_phone))
        cust_id = cursor.lastrowid
        cursor.execute("INSERT INTO orders (customer_id, timestamp, items, total_price) VALUES (?, ?, ?, ?)", 
                       (cust_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), json.dumps(st.session_state.cart), total))
        conn.commit(); conn.close()
        st.success("Order Saved!")
        time.sleep(2)
        st.session_state.clear()
        st.rerun()

    if st.button("🚀 COMPLETE ORDER"):
        if not st.session_state.cart:
            st.warning("Tray is empty!")
        else:
            st.session_state.checkout_step = "GET_NAME"
            st.info("Say your full name.")

    if st.button("🗑️ CLEAR TRAY"):
        st.session_state.cart = {}
        st.session_state.checkout_step = "IDLE"
        st.rerun()