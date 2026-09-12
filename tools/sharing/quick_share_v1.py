#!/usr/bin/env python3
"""
QUICK SHARE - One-click sharing for any project
"""

import zipfile
import os
import sys
from pathlib import Path
import urllib.parse

def create_ai_shareable_bundle(project_path):
    """Create the perfect bundle for AI review"""
    output_zip = "ai_review_bundle.zip"
    
    with zipfile.ZipFile(output_zip, 'w') as zipf:
        # Include key files only
        important_files = []
        
        for pattern in ['*.py', '*.js', '*.ts', '*.tsx', '*.json', '*.md', 'package.json', 'requirements.txt']:
            for file_path in Path(project_path).rglob(pattern):
                # Skip junk directories
                if any(junk in file_path.parts for junk in ['node_modules', '.git', 'dist', 'build']):
                    continue
                
                # Add file to zip
                arcname = file_path.relative_to(project_path)
                zipf.write(file_path, arcname)
                important_files.append(str(arcname))
    
    print(f"🎯 Created AI review bundle with {len(important_files)} files")
    print(f"📦 File: {output_zip}")
    print(f"📏 Size: {os.path.getsize(output_zip) / 1024 / 1024:.2f} MB")
    
    return output_zip

def share_instructions(bundle_path):
    """Print sharing instructions"""
    print("\n" + "="*50)
    print("🚀 HOW TO SHARE WITH AI:")
    print("="*50)
    print("1. UPLOAD TO CLOUD:")
    print("   - Google Drive: drive.google.com")
    print("   - Dropbox: dropbox.com") 
    print("   - GitHub Gist: gist.github.com")
    print("   - Pastebin: pastebin.com")
    print()
    print("2. OR EMAIL IT:")
    print("   Just attach the zip file to any email")
    print()
    print("3. GET A SHAREABLE LINK AND PASTE IT IN CHAT")
    print("="*50)

if __name__ == "__main__":
    target_path = sys.argv[1] if len(sys.argv) > 1 else "."
    
    if not os.path.exists(target_path):
        print(f"❌ Path not found: {target_path}")
        sys.exit(1)
    
    bundle = create_ai_shareable_bundle(target_path)
    share_instructions(bundle)