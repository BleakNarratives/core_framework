#!/usr/bin/env python3
"""
CLIPBOARD DEBUGGER - Let's see what's actually happening
"""
import subprocess
import time

def get_clipboard():
    try:
        result = subprocess.check_output(['termux-clipboard-get']).decode().strip()
        return result
    except Exception as e:
        return f"ERROR: {e}"

print("🔍 Clipboard Debugger - Testing every 3 seconds...")
print("Copy some text from DeepSeek and watch here...")

while True:
    clipboard = get_clipboard()
    print(f"📋 Clipboard: {clipboard[:50]}...")
    time.sleep(3)
