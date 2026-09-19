import os
import shutil
import logging
from datetime import datetime

# --- CRITICAL CONFIGURATION: USB DRIVE PATH ---
# This path is set to your mini USB card's location:
UNSORTED_ROOT = '/storage/68CC-9ED6/BleakDev' 

# Define your target project roots and subdirectories
BACKEND_ROOT = os.path.join(UNSORTED_ROOT, 'modmind-brains')
FRONTEND_ROOT = os.path.join(UNSORTED_ROOT, 'modmind-mask')
FRONTEND_SRC = os.path.join(FRONTEND_ROOT, 'src')
FRONTEND_SRC_COMPONENTS = os.path.join(FRONTEND_SRC, 'components')

# Define file extensions and the specific sub-path where they belong
FILE_MAP = {
    # Backend Files (Python)
    '.py': BACKEND_ROOT,
    '.env': BACKEND_ROOT,
    
    # --- Special Cases for Frontend Root ---
    # App.tsx is the entry point, so it goes in 'src'
    'App.tsx': FRONTEND_SRC, 
    
    # --- Default Frontend Component Files ---
    '.tsx': FRONTEND_SRC_COMPONENTS,
    '.ts': FRONTEND_SRC_COMPONENTS,
    '.js': FRONTEND_SRC_COMPONENTS,
    
    # We explicitly map the common components to ensure they land correctly
    'FloatingOrbMenu.tsx': FRONTEND_SRC_COMPONENTS,
    'ErrorBoundary.tsx': FRONTEND_SRC_COMPONENTS,
    'Dashboard.tsx': FRONTEND_SRC_COMPONENTS,
}

# Setup Logging to save a record of the "bitch work"
log_file = os.path.join(UNSORTED_ROOT, f"file_organizer_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
logging.basicConfig(filename=log_file, level=logging.INFO,
                    format='%(asctime)s - %(message)s', datefmt='%H:%M:%S')

def ensure_directory_structure():
    """Ensures all necessary project directories exist before moving files."""
    directories = [BACKEND_ROOT, FRONTEND_SRC_COMPONENTS]
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"-> Created directory: {directory}")
            logging.info(f"DIRECTORY CREATED: {directory}")

def organize_files():
    """Scans the UNSORTED_ROOT and moves files based on FILE_MAP."""
    ensure_directory_structure()
    
    print("\nStarting ModMind File Organization Automation...")
    logging.info("--- STARTING FILE ORGANIZATION ---")
    
    files_moved = 0
    files_skipped = 0
    
    # Scan only the top level of the unsorted root directory
    for item in os.listdir(UNSORTED_ROOT):
        source_path = os.path.join(UNSORTED_ROOT, item)
        
        # Skip directories, the script itself, and its log file
        if os.path.isdir(source_path) or item == os.path.basename(log_file) or item == os.path.basename(__file__):
            continue
            
        file_name, file_ext = os.path.splitext(item)
        target_dir = None
        
        # 1. Check for specific full file name matches (e.g., 'App.tsx' goes to 'src')
        if item in FILE_MAP:
            target_dir = FILE_MAP[item]
        # 2. Check for extension matches (e.g., '.py' goes to 'modmind-brains')
        elif file_ext in FILE_MAP:
            target_dir = FILE_MAP[file_ext]
        
        if target_dir:
            try:
                # Ensure the destination path exists before moving
                os.makedirs(target_dir, exist_ok=True)
                
                destination_path = os.path.join(target_dir, item)
                shutil.move(source_path, destination_path)
                
                # Report relative path for cleaner output
                print(f"MOVED: {item} -> {os.path.relpath(target_dir, UNSORTED_ROOT)}")
                logging.info(f"MOVED: {item} -> {destination_path}")
                files_moved += 1
            except Exception as e:
                print(f"ERROR moving {item}: {e}")
                logging.error(f"ERROR moving {item}: {e}")
                files_skipped += 1
        else:
            print(f"SKIPPED: {item} (Unknown type or target not defined)")
            logging.warning(f"SKIPPED: {item} (No target defined in FILE_MAP)")
            files_skipped += 1

    logging.info("--- FILE ORGANIZATION COMPLETE ---")
    print(f"\n--- Summary ---")
    print(f" Files Moved: {files_moved}")
    print(f" Files Skipped: {files_skipped}")
    print(f"Log saved to: {os.path.basename(log_file)}")


if __name__ == "__main__":
    organize_files()
