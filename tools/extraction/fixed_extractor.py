# FILE: /storage/emulated/0/code_tool/fixed_extractor.py
# RUN: python3 fixed_extractor.py

import subprocess
import re

def main():
    print("🎯 FIXED EXTRACTOR - ACTUALLY WORKS")
    print("=" * 40)
    
    try:
        # Get clipboard
        result = subprocess.run(["termux-clipboard-get"], capture_output=True, text=True)
        text = result.stdout
        
        if not text.strip():
            print("❌ Clipboard empty!")
            return
        
        print(f"📋 Clipboard length: {len(text)}")
        print("First 100 chars:")
        print(text[:100])
        
        # SIMPLE REGEX THAT ACTUALLY WORKS
        # Look for anything between triple backticks
        blocks = re.findall(r'```(.*?)```', text, re.DOTALL)
        
        if not blocks:
            print("❌ No code blocks found with ```pattern")
            print("Trying alternative patterns...")
            # Try other common code block formats
            blocks = re.findall(r'``(.*?)``', text, re.DOTALL)
            if not blocks:
                blocks = re.findall(r'`(.*?)`', text, re.DOTALL)
        
        if not blocks:
            print("❌ STILL NO CODE BLOCKS!")
            print("Clipboard content:")
            print(text[:500])
            return
        
        print(f"📦 Found {len(blocks)} code blocks!")
        
        # Save them
        for i, code in enumerate(blocks):
            filename = f"extracted_code_{i+1}.txt"
            with open(filename, 'w') as f:
                f.write(code.strip())
            print(f"💾 {filename}")
            print(f"   Preview: {code.strip()[:50]}...")
        
        print("✅ EXTRACTION SUCCESSFUL!")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()