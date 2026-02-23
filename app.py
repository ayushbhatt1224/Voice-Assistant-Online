import ollama
from faster_whisper import WhisperModel
from kokoro import KPipeline
import sounddevice as sd
import pyaudio
import wave

# --- PART 1: THE RECORDER ---
def record_audio(filename="input.wav", seconds=5):
    CHUNK = 1024
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000
    p = pyaudio.PyAudio()
    stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
    print(f"\n>>> RECORDING (Hindi or English)...")
    frames = [stream.read(CHUNK) for _ in range(0, int(RATE / CHUNK * seconds))]
    stream.stop_stream(); stream.close(); p.terminate()
    wf = wave.open(filename, 'wb')
    wf.setnchannels(CHANNELS); wf.setsampwidth(p.get_sample_size(FORMAT)); wf.setframerate(RATE)
    wf.writeframes(b''.join(frames)); wf.close()

# --- PART 2: THE MODELS ---
print("Loading Ears (Whisper)...")
stt_model = WhisperModel("base", device="cpu", compute_type="int8") 

# Load two pipelines: one for English (a), one for Hindi (h)
print("Loading Voices...")
pipelines = {
    'en': KPipeline(lang_code='a'),
    'hi': KPipeline(lang_code='h')
}

def run_foodchain():
    record_audio("input.wav", seconds=5)
    
    # 1. Speech-to-Text with Language Detection
    segments, info = stt_model.transcribe("input.wav", beam_size=5)
    user_text = "".join([s.text for s in segments]).strip()
    detected_lang = info.language # 'hi' for Hindi, 'en' for English
    
    if not user_text:
        return

    print(f"Detected ({detected_lang}): {user_text}")

    # 2. Brain (Ollama) - Instruct to stay in detected language
    response = ollama.chat(model='qwen2.5:3b', messages=[
        {'role': 'system', 'content': f'You are a restaurant assistant. Reply ONLY in the language code: {detected_lang}. Be very brief.'},
        {'role': 'user', 'content': user_text},
    ])
    reply = response['message']['content']
    print(f"Assistant: {reply}")

    # 3. Voice (Kokoro) - Switch voice based on language
    lang_key = 'hi' if detected_lang == 'hi' else 'en'
    voice_name = 'hf_alpha' if lang_key == 'hi' else 'af_heart'
    
    generator = pipelines[lang_key](reply, voice=voice_name, speed=1)
    for _, _, audio in generator:
        sd.play(audio, 24000)
    sd.wait() 

if __name__ == "__main__":
    print("\n--- Multilingual FoodChain AI Ready! ---")
    while True:
        run_foodchain()
        input("\n[Enter to talk again]")