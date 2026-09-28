#!/usr/bin/env python3
"""
Sensor Listener (sensor_listener.py)
Hardened version: production-grade audio monitoring.
"""

import sounddevice as sd
import numpy as np
import json
import sys
import logging
import argparse
from pathlib import Path
from datetime import datetime

# Setup Logging
LOG_FILE = Path.home() / "logs" / "sensor_listener.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stderr)]
)

def emit_event(event_type: str, value: float):
    """Emits a structured JSON event to stdout."""
    event = {"event": event_type, "value": round(value, 4), "ts": datetime.now().isoformat()}
    print(json.dumps(event))
    sys.stdout.flush()

class AudioMonitor:
    def __init__(self, amp_threshold: float, hf_threshold: float, samplerate: int):
        self.amp_threshold = amp_threshold
        self.hf_threshold = hf_threshold
        self.samplerate = samplerate

    def audio_callback(self, indata, frames, time_info, status):
        if status:
            logging.warning(f"Audio buffer status: {status}")
            return

        try:
            # RMS Amplitude
            rms = np.sqrt(np.mean(indata**2))
            
            # FFT High-Frequency Analysis
            fft_data = np.abs(np.fft.rfft(indata[:, 0]))
            hf_power = np.mean(fft_data[int(len(fft_data)*0.8):]) 

            if rms > self.amp_threshold:
                emit_event("amplitude_spike", rms)
            
            if hf_power > self.hf_threshold:
                emit_event("high_freq_spike", hf_power)
                
        except Exception as e:
            logging.error(f"Error in audio callback: {e}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--amp", type=float, default=0.05)
    parser.add_argument("--hf", type=float, default=0.01)
    parser.add_argument("--rate", type=int, default=44100)
    args = parser.parse_args()

    monitor = AudioMonitor(args.amp, args.hf, args.rate)
    
    logging.info(f"Starting listener: Rate={args.rate}, AmpThr={args.amp}, HFThr={args.hf}")
    
    try:
        with sd.InputStream(callback=monitor.audio_callback, channels=1, samplerate=args.rate, blocksize=1024):
            while True:
                time.sleep(1)
    except Exception as e:
        logging.critical(f"Fatal error in audio stream: {e}")
        sys.exit(1)

if __name__ == "__main__":
    import time
    main()
