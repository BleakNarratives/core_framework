import time
import pyperclip
import subprocess
import threading
import sys

# Minimalist, low-latency satirical transformer for Snarkie
def transform_to_snark(text):
    # Extremely concise to keep inference < 500ms
    # Replace with a fast local inference call in production
    snark = f"Oh look, you copied '{text[:20]}...'. Groundbreaking, Snarkie says."
    return snark

def speak(text):
    # Non-blocking TTS (async subprocess)
    try:
        # Assuming 'say' (macOS) or 'spd-say' (Linux)
        subprocess.Popen(['say', text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        print(f"Snarkie says: {text}")

def monitor_clipboard():
    last_content = pyperclip.paste()
    print("Snarkie is listening... (Ctrl+C to stop)")
    try:
        while True:
            current_content = pyperclip.paste()
            if current_content != last_content and current_content.strip():
                last_content = current_content
                snarky_comment = transform_to_snark(current_content)
                speak(snarky_comment)
            time.sleep(0.5) # Polling interval
    except KeyboardInterrupt:
        print("\nSnarkie signing off.")
        sys.exit(0)

if __name__ == "__main__":
    monitor_clipboard()
