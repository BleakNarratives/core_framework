#!/usr/bin/env python3
"""
NO-BULLSHIT CHAT SCRAPER - Actually extracts code from DeepSeek responses
"""
import re
import subprocess
import os
from datetime import datetime

def speak(text):
    """TTS that actually works"""
    subprocess.run(['espeak', '-s', '160', text])

def extract_and_save_all_code(chat_text):
    """Extract every code block and save immediately"""
    code_blocks = re.findall(r'```(?:python)?\s*(.*?)```', chat_text, re.DOTALL)
    
    if not code_blocks:
        speak("No code blocks found")
        return []
    
    saved_files = []
    for i, code in enumerate(code_blocks):
        filename = f"deepseek_code_{datetime.now().strftime('%H%M%S')}_{i}.py"
        with open(filename, 'w') as f:
            f.write(code.strip())
        saved_files.append(filename)
        print(f" SAVED: {filename}")
    
    speak(f"Saved {len(saved_files)} code files")
    return saved_files

# IMMEDIATE ACTION - NO PROMPTS
print(" DEEPSEEK CODE EXTRACTOR - PASTE RESPONSE NOW:")
chat_response = input()
extract_and_save_all_code(chat_response)
print(" DONE - Check your files")
