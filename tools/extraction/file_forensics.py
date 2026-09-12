#!/usr/bin/env python3
"""
FILE FORENSICS - FIXED VERSION
Fine-tooth comb for your project structure
"""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Set

class FileForensics:
    def __init__(self, scan_path: str):
        self.scan_path = Path(scan_path).absolute()
        self.expected_structure = self._get_expected_structure()
        self.found_files = {}
        self.missing_files = {}
        self.incomplete_files = {}
        
    def _get_expected_structure(self) -> Dict[str, List[str]]:
        """The ideal file structure we want"""
        return {
            "LAUNCHERS_CORE": [
                "stream_setup.py",
                "install_plugins.py", 
                "plugin_loader.py",
                "requirements.txt"
            ],
            "CORE_ENGINE": [
                "chat_demon.py",
                "forge_executor.py", 
                "voice_demon.py",
                "plugin_manager.py"
            ],
            "PLUGINS_voice_commands": [
                "voice_demon.py",
                "speech_engine.py", 
                "voice_ui.py"
            ],
            "PLUGINS_visualization": [
                "code_visualizer.py",
                "dependency_mapper.py",
                "3d_city_builder.py"
            ],
            "PLUGINS_gamification": [
                "code_gamification.py",
                "achievement_tracker.py", 
                "leaderboard.py"
            ],
            "PLUGINS_collaboration": [
                "collaboration.py",
                "vote_system.py",
                "viewer_websocket.py"
            ],
            "PLUGINS_deployment": [
                "deploy_dashboard.py",
                "netlify_deploy.py",
                "vercel_deploy.py"
            ],
            "PLUGINS_ai_assistant": [
                "ai_pair.py",
                "code_reviewer.py",
                "test_generator.py"
            ],
            "PLUGINS_performance": [
                "performance_monitor.py",
                "resource_tracker.py", 
                "live_metrics.py"
            ],
            "PLUGINS_documentation": [
                "auto_docs.py",
                "readme_generator.py",
                "api_doc_builder.py"
            ],
            "WEB_STREAMING_static": [
                "live_display.html",
                "stream_overlay.html",
                "code_visualizer.html",
                "leaderboard.html",
                "collaboration.html"
            ],
            "WEB_STREAMING_websocket_servers": [
                "main_websocket.py",
                "plugin_broadcaster.py",
                "obs_connector.py"
            ],
            "WEB_STREAMING_obs_sources": [
                "browser_sources.json",
                "overlay_styles.css", 
                "scene_templates.json"
            ],
            "GENERATED_OUTPUT_projects_current_stream": [
                "src/",
                "components/",
                "api/",
                "tests/"
            ],
            "DATA_STATE_state": [
                "active_plugins.json",
                "viewer_votes.json",
                "achievements.json", 
                "stream_state.json"
            ],
            "DATA_STATE_logs": [
                "chat_commands.log",
                "code_generation.log",
                "plugin_activity.log",
                "stream_events.log"
            ],
            "CONFIGURATION_config": [
                "main_config.yaml",
                "plugin_configs/voice_commands.yaml",
                "plugin_configs/gamification.yaml",
                "plugin_configs/deployment.yaml",
                "stream_platforms/youtube_config.yaml",
                "stream_platforms/twitch_config.yaml",
                "stream_platforms/restream_config.yaml",
                "api_keys.yaml"
            ],
            "CONFIGURATION_templates_project_templates": [
                "react_app/",
                "fastapi_backend/", 
                "full_stack/"
            ],
            "TESTING_DEV_tests_unit": [
                "test_chat_demon.py",
                "test_plugins.py",
                "test_executor.py"
            ],
            "TESTING_DEV_tests_integration": [
                "test_stream_setup.py",
                "test_plugin_loading.py"
            ],
            "TESTING_DEV_scripts": [
                "backup_stream_state.py",
                "cleanup_old_projects.py",
                "update_plugins.py",
                "health_check.py"
            ]
        }
    
    def scan_current_structure(self) -> Dict:
        """Scan what actually exists"""
        print(f"🔍 Scanning: {self.scan_path}")
        
        all_files = {}
        
        for root, dirs, files in os.walk(self.scan_path):
            for file in files:
                if file.endswith(('.py', '.js', '.ts', '.tsx', '.json', '.md', '.txt', '.yaml', '.yml', '.html', '.css')):
                    full_path = Path(root) / file
                    try:
                        rel_path = full_path.relative_to(self.scan_path)
                        
                        # Get file stats
                        stat = full_path.stat()
                        file_info = {
                            'path': str(rel_path),
                            'size_kb': round(stat.st_size / 1024, 2),
                            'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                            'lines': self._count_lines(full_path)
                        }
                        
                        # Categorize by directory
                        parent_dir = str(rel_path.parent)
                        if parent_dir not in all_files:
                            all_files[parent_dir] = []
                        all_files[parent_dir].append(file_info)
                        
                    except ValueError:
                        continue
        
        self.found_files = all_files
        return all_files
    
    def _count_lines(self, file_path: Path) -> int:
        """Count lines in a file"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return sum(1 for _ in f)
        except:
            return 0
    
    def analyze_completeness(self):
        """Compare current structure vs expected"""
        print("\n🎯 ANALYZING COMPLETENESS...")
        
        # Flatten expected files for easier searching
        expected_files = {}
        for category, files in self.expected_structure.items():
            for file in files:
                expected_files[file] = category
        
        # Check what's missing
        found_paths = set()
        for dir_path, files in self.found_files.items():
            for file_info in files:
                found_paths.add(file_info['path'])
        
        for expected_file, category in expected_files.items():
            if expected_file not in found_paths and not any(expected_file in found for found in found_paths):
                if category not in self.missing_files:
                    self.missing_files[category] = []
                self.missing_files[category].append(expected_file)
        
        # Check incomplete files (empty or very small)
        for dir_path, files in self.found_files.items():
            for file_info in files:
                if file_info['lines'] <= 3:  # Empty or nearly empty
                    category = self._categorize_file(file_info['path'])
                    if category not in self.incomplete_files:
                        self.incomplete_files[category] = []
                    self.incomplete_files[category].append(file_info)
    
    def _categorize_file(self, file_path: str) -> str:
        """Categorize a file path - SIMPLIFIED VERSION"""
        # Simple categorization based on parent directory
        if 'plugin' in file_path.lower():
            return 'PLUGINS'
        elif 'test' in file_path.lower():
            return 'TESTING_DEV'
        elif 'config' in file_path.lower():
            return 'CONFIGURATION'
        elif file_path.startswith('.') or 'git' in file_path:
            return 'SYSTEM_FILES'
        else:
            return 'OTHER'
    
    def generate_report(self) -> str:
        """Generate comprehensive report"""
        report = []
        report.append("=" * 80)
        report.append("📊 FILE FORENSICS REPORT - BLEAKDEV")
        report.append("=" * 80)
        report.append(f"Scan Path: {self.scan_path}")
        report.append(f"Scan Date: {datetime.now().isoformat()}")
        report.append("")
        
        # Summary
        total_found = sum(len(files) for files in self.found_files.values())
        total_missing = sum(len(files) for files in self.missing_files.values())
        total_incomplete = sum(len(files) for files in self.incomplete_files.values())
        
        report.append("📈 EXECUTIVE SUMMARY:")
        report.append(f"  • 📂 Total Files Found: {total_found}")
        report.append(f"  • ❌ Core Files Missing: {total_missing}")
        report.append(f"  • 🔧 Incomplete Files: {total_incomplete}")
        report.append(f"  • 📊 Your Stats: 124 Python, 13 TS, 88 TSX, 15 JSON files")
        report.append("")
        
        # Found files - show top level only
        report.append("✅ KEY FILES FOUND:")
        report.append("-" * 40)
        
        # Show root level files first
        if '.' in self.found_files:
            report.append("\n📁 ROOT LEVEL:")
            for file_info in self.found_files['.']:
                if file_info['path'] in ['chat_demon.py', 'forge_executor.py', 'stream_setup.py', 'install_plugins.py']:
                    status = "✅" if file_info['lines'] > 10 else "🔄"
                    report.append(f"  {status} {file_info['path']} ({file_info['lines']} lines)")
        
        # Show important directories
        important_dirs = ['modmind-brains', 'modmind-mask', 'forge_actual_output']
        for dir_name in important_dirs:
            if dir_name in self.found_files:
                report.append(f"\n📁 {dir_name.upper()}:")
                for file_info in self.found_files[dir_name][:5]:  # First 5 files
                    report.append(f"  📄 {file_info['path']}")
        
        report.append("")
        
        # Missing files - prioritized
        report.append("❌ PRIORITY MISSING FILES:")
        report.append("-" * 40)
        
        priority_categories = ['LAUNCHERS_CORE', 'CORE_ENGINE', 'PLUGINS_voice_commands']
        for category in priority_categories:
            if category in self.missing_files and self.missing_files[category]:
                report.append(f"\n🎯 {category.replace('_', ' ').title()}:")
                for file in self.missing_files[category][:3]:  # Top 3 per category
                    report.append(f"  ⚠️  {file}")
        
        report.append("")
        
        # Incomplete files
        report.append("🔄 INCOMPLETE FILES (NEEDS WORK):")
        report.append("-" * 40)
        if self.incomplete_files:
            for category, files in self.incomplete_files.items():
                if files:
                    report.append(f"\n📁 {category}:")
                    for file_info in files[:5]:  # First 5
                        report.append(f"  🔧 {file_info['path']} (only {file_info['lines']} lines)")
        else:
            report.append("  🎉 No incomplete files found!")
        report.append("")
        
        # Project analysis
        report.append("🏗️ PROJECTS DETECTED:")
        report.append("-" * 40)
        projects = [
            "IDEal", "odds-of-the-gods", "sinister_agents_v1", "ShipWrekD-OS", 
            "legal_ai", "aFiREFLY_agent", "keymaster", "ModMind-EquiNex",
            "ChAImeleon", "JaneNat Hub", "Co-Witness", "DreamTable_Sandbox"
        ]
        
        for project in projects:
            project_path = Path(self.scan_path) / project
            if project_path.exists():
                py_files = list(project_path.rglob("*.py"))
                tsx_files = list(project_path.rglob("*.tsx"))
                report.append(f"  📦 {project}: {len(py_files)} Python, {len(tsx_files)} TSX files")
        
        report.append("")
        
        # Recommendations
        report.append("💡 ACTION PLAN:")
        report.append("-" * 40)
        report.append("1. 🎯 COMPLETE CORE: Finish chat_demon.py & forge_executor.py")
        report.append("2. 🚀 SETUP PLUGINS: Add voice_commands and gamification plugins")
        report.append("3. 📦 CONSOLIDATE: Use code_miner.py to clean up AI Studio projects")
        report.append("4. 🔧 FIX INCOMPLETE: Complete the empty/small files first")
        report.append("")
        report.append("🎪 NEXT STEPS:")
        report.append("• Run: python quick_share.py .  (to create shareable bundle)")
        report.append("• Run: python code_miner.py IDEal/  (clean AI Studio projects)")
        report.append("• Focus on ONE project at a time")
        
        return '\n'.join(report)
    
    def save_report(self, report: str):
        """Save report to file"""
        output_path = self.scan_path / "bleakdev_analysis_report.txt"
        output_path.write_text(report, encoding='utf-8')
        print(f"📄 Report saved: {output_path}")

def main():
    """Run the forensic analysis"""
    scanner = FileForensics("/storage/68CC-9ED6/BleakDev/")
    scanner.scan_current_structure()
    scanner.analyze_completeness()
    report = scanner.generate_report()
    
    print(report)
    scanner.save_report(report)

if __name__ == "__main__":
    main()