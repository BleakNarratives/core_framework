#!/usr/bin/env python3
"""
IMMEDIATE CODE EXTRACTOR - Actually extracts and speaks code
NO LOOP BULLSHIT - ONE-TIME EXTRACTION
"""
import subprocess
import re
import sys

def speak(text):
    """Make it actually SPEAK"""
    try:
        clean_text = text.replace('"', '\\"').replace('$', '\\$')
        subprocess.run(['espeak', '-s', '160', '-p', '50', clean_text])
        print(f": {text}")
    except Exception as e:
        print(f": {e}")

def extract_code(text):
    """Extract code blocks from text"""
    # Match ```python ... ``` or ``` ... ```
    code_blocks = re.findall(r'```(?:python)?\s*(.*?)```', text, re.DOTALL)
    return [block.strip() for block in code_blocks if block.strip()]

def main():
    speak("Code extractor ready for immediate action")
    print(" PASTE THE ENTIRE CHAT RESPONSE WITH CODE BLOCKS:")
    print("(Press Ctrl+D when done on empty line)\n")
    
    # Read ALL input until Ctrl+D
    full_input = sys.stdin.read()
    
    print(" EXTRACTING CODE BLOCKS...")
    code_blocks = extract_code(full_input)
    
    if code_blocks:
        speak(f"Found {len(code_blocks)} code blocks")
        for i, code in enumerate(code_blocks):
            filename = f"extracted_code_{i+1}.py"
            with open(filename, 'w') as f:
                f.write(code)
            print(f" SAVED: {filename}")
            speak(f"Saved code block {i+1}")
            
        print(f" SUCCESS: Extracted {len(code_blocks)} code files")
        speak("Code extraction complete")
    else:
        print(" NO CODE BLOCKS FOUND")
        speak("No code blocks detected in the response")

if __name__ == "__main__":
    main()
