# Giggs Voice Assistant: Commercial FoodChain AI Kiosk
## 🚀 Project Overview
Giggs Voice Assistant is a professional-grade, local-first AI kiosk designed for high-traffic restaurant environments.This system bridges the gap between raw AI and commercial usability.

It features a Hybrid NLU Engine that runs efficiently on mid-range hardware (i3 processors) by combining lightweight Large Language Models (LLMs) with robust Python-based state machines.

## 🛠️ Key Technical Implementations

### 1. Hybrid NLU & Intent Engine

The system utilizes a custom "Segment Scanner" to process natural language.

Contextual Logic: Correctly handles mixed commands like "Add one burger but remove the chai."

Fuzzy Semantic Matching: Uses thefuzz library to map casual user speech (e.g., "burger") to formal database entries (e.g., "Classic Veg Burger").

Numerical Extraction: Employs a Regex-based pre-processor to ensure quantity accuracy (e.g., "two," "2," or "do").

### 2. Relational Database Schema (SQLite)

The application is built on a structured SQLite backend to ensure data persistence and analytics:

Menu Table: Real-time synchronization of items, prices, and upselling logic.

CRM (Customers Table): Stores customer names and phone numbers.

Orders Table: Links transactions to customers via Foreign Keys for professional reporting.

AI Knowledge Base: Allows for "In-Context Learning" (ICL) updates without modifying source code.

### 3. High-Performance Local Stack

STT: Faster-Whisper (Base model, int8 quantization) for near-instant transcription.

LLM: Ollama (Qwen2.5-0.5b) for intent classification.

TTS: Kokoro-82M for human-like vocal responses.

## 📁 Project Structure

Plaintext

├── app.py                # Main Streamlit logic & Hybrid Engine

├── foodchain_pro.db      # SQLite Relational Database

├── input.wav             # Buffer for STT processing

├── requirements.txt      # Project dependencies

└── README.md             # Documentation

## ⚙️ Installation & Setup
Clone the Repository:

**Bash**
``git clone https://bitbucket.org/your-profile/foodchain-ai.git``
cd foodchain-ai

**Install Dependencies:**

To install all the libraries and framework:

**Bash**

``pip install streamlit ollama faster-whisper kokoro sounddevice pyaudio thefuzz python-Levenshtein pandas numpy``


**Bash**

``pip install -r requirements.txt``

Setup Ollama: Download and run Ollama, then pull the model:

**Bash**

``ollama pull qwen2.5:0.5b``

Launch the Kiosk:

**Bash**

``streamlit run app.py``

### 2. The Requirements File (requirements.txt)
Create a file named requirements.txt and add these links/libraries:

Plaintext
#### UI & Web

streamlit>=1.30.0

#### AI & NLP

ollama>=0.1.0

faster-whisper>=0.10.0

thefuzz>=0.20.0

python-Levenshtein>=0.23.0

#### Audio Processing
sounddevice>=0.4.6

pyaudio>=0.2.14

kokoro>=0.0.1

#### Data Processing

pandas>=2.0.0

numpy>=1.24.0

### 3. Links for your Bitbucket Documentation

If you want to add external links to the "Resources" section of your Bitbucket project, here are the official references for the technology you used:

**Ollama (Local LLM):** ``https://ollama.com/library/qwen2.5``

**Faster-Whisper (STT):** ``https://github.com/SYSTRAN/faster-whisper``

**Kokoro (TTS):** ``https://huggingface.co/hexgrad/Kokoro-82M``

**TheFuzz (Fuzzy Matching):** ``https://github.com/seatgeek/thefuzz``



**What you have achieved:**



This setup proves that you can build a full-stack AI application that is:

**Hardware-aware:** Optimized to run on an i3.

**Database-driven:** Uses SQL instead of simple text files.

**User-centric:** Handles conversational errors and provides a professional checkout flow.

## Developed by : Ayush Bhatt and Krishna Kumar Jha