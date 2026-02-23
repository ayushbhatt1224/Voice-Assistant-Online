import json
import sqlite3
import os

# --- SETTINGS ---
JSON_FILE = 'intents.json' 
DB_NAME = 'foodchain_pro.db'

def import_data():
    if not os.path.exists(JSON_FILE):
        print(f"❌ Error: Could not find '{JSON_FILE}' in {os.getcwd()}")
        return

    try:
        with open(JSON_FILE, 'r') as f:
            data = json.load(f)
        
        # Handle different JSON structures
        intents_list = data['intents'] if isinstance(data, dict) and 'intents' in data else data
        
        if not isinstance(intents_list, list):
            print("❌ Error: The JSON structure is not recognized as a list of intents.")
            return

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # --- NEW: TABLE CREATION (Ensures no "no such table" error) ---
        cursor.execute('''CREATE TABLE IF NOT EXISTS nlu_dataset 
                          (text_query TEXT, intent TEXT, item TEXT, qty INTEGER)''')
        
        count = 0
        for intent_entry in intents_list:
            tag = intent_entry.get('tag', 'unknown')
            patterns = intent_entry.get('patterns', [])
            
            # Keywords to filter for restaurant-related intents
            relevant_keywords = ['restaurant', 'food', 'order', 'greet', 'bye', 'menu', 'eat', 'drink']
            is_relevant = any(k in tag.lower() for k in relevant_keywords)
            
            if is_relevant:
                # Map dataset tag to Giggs Assistant intents
                internal_intent = "ADD" if any(x in tag.lower() for x in ["order", "food", "item"]) else "GREETING"
                
                for pattern in patterns:
                    cursor.execute(
                        "INSERT INTO nlu_dataset (text_query, intent, item, qty) VALUES (?, ?, ?, ?)",
                        (pattern, internal_intent, "generic", 1)
                    )
                    count += 1
        
        conn.commit()
        conn.close()
        print(f"✅ Success! Imported {count} restaurant-related examples into {DB_NAME}.")

    except Exception as e:
        print(f"❌ An error occurred: {e}")

if __name__ == "__main__":
    import_data()