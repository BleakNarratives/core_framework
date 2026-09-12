#!/usr/bin/env python3
"""
FILE FORENSICS WITH TTS - Talks while it works
"""

import os
from pathlib import Path
from datetime import datetime
from tts_announcer import CodeAnnouncer

class TalkingFileForensics:
    def __init__(self, scan_path: str, tts_enabled=True):
        self.scan_path = Path(scan_path).absolute()
        self.tts = CodeAnnouncer(enabled=tts_enabled)
        
    def scan_and_announce(self):
        """Scan with live commentary"""
        self.tts.speak("Starting file forensics scan")
        print("🔍 Scanning file structure...")
        
        # Simulate scanning process
        file_count = 0
        for root, dirs, files in os.walk(self.scan_path):
            for file in files:
                if file.endswith('.py'):
                    file_count += 1
                    if file_count % 20 == 0:  # Announce every 20 files
                        self.tts.speak(f"Found {file_count} Python files so far")
        
        self.tts.speak(f"Scan complete. Found {file_count} Python files total")
        return file_count

def main():
    """Run talking forensic analysis"""
    forensics = TalkingFileForensics("/storage/68CC-9ED6/BleakDev/", tts_enabled=True)
    
    print("🎤 TALKING FILE ANALYSIS STARTING...")
    file_count = forensics.scan_and_announce()
    
    # Summary announcement
    summary = f"Analysis complete. Your BleakDev project contains {file_count} Python files across multiple projects. Ready for refactoring."
    forensics.tts.speak(summary)
    
    print(f"\n📊 {summary}")

if __name__ == "__main__":
    main()