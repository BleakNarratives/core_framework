class CodeGamification:
    def __init__(self):
        self.achievements = {
            "first_bug": {"name": " Bug Hunter", "unlocked": False},
            "ten_commits": {"name": " Productive", "unlocked": False},
            "live_deploy": {"name": " Deploy Master", "unlocked": False},
            "voice_command": {"name": " Voice Coder", "unlocked": False}
        }
        self.points = 0
        self.level = 1
    
    def check_achievements(self, action, metadata):
        """Check and unlock achievements"""
        if action == "file_created" and metadata.get('type') == 'bug_fix':
            self.unlock_achievement("first_bug")
        
        if action == "deployment_success":
            self.unlock_achievement("live_deploy")
            
        if action == "voice_command":
            self.unlock_achievement("voice_command")
    
    def unlock_achievement(self, achievement_id):
        if not self.achievements[achievement_id]["unlocked"]:
            self.achievements[achievement_id]["unlocked"] = True
            self.points += 100
            self.check_level_up()
            
            print(f" ACHIEVEMENT UNLOCKED: {self.achievements[achievement_id]['name']}")
            self.broadcast_achievement(achievement_id)
    
    def check_level_up(self):
        if self.points >= self.level * 500:
            self.level += 1
            print(f" LEVEL UP! Now level {self.level}")
    
    def get_leaderboard_html(self):
        """Generate leaderboard for OBS overlay"""
        return f"""
        <div class="leaderboard">
            <h3> CODING GAME</h3>
            <p>Level: {self.level} | Points: {self.points}</p>
            <div class="achievements">
                {' '.join([f"<span class={'unlocked' if ach['unlocked'] else 'locked'}>{ach['name']}</span>" 
                          for ach in self.achievements.values()])}
            </div>
        </div>
        """