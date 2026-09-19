#!/usr/bin/env python3
"""
CLIPBOARD MONITOR - Watches for new text in clipboard
Requires termux-clipboard-get
"""
import subprocess
import time

def speak(text):
    subprocess.run(['espeak', '-s', '160', text])

def get_clipboard():
    try:
        return subprocess.check_output(['termux-clipboard-get']).decode().strip()
    except:
        return ""

print(" Monitoring clipboard for DeepSeek responses...")
print("COPY text from DeepSeek web interface to trigger speaking")

last_clipboard = ""

while True:
    current = get_clipboard()
    if current and current != last_clipboard and len(current) > 50:
        print(" NEW RESPONSE COPIED!")
        speak("New DeepSeek response detected")
        # Speak first meaningful part
        lines = current.split('\n')
        for line in lines[:3]:  # Speak first 3 lines
            if len(line) > 20:
                speak(line[:100])
        last_clipboard = current
    
    time.sleep(3)
