class DiscoveryEngine:
    """
    Identifies content opportunities based on audience insights.
    """
    def __init__(self, audience_manager):
        self.audience_manager = audience_manager

    def discover_topics(self):
        insights = self.audience_manager.get_insights()
        topics = []
        
        # Rule: Problems/Frustrations -> Solution-focused content
        for problem in insights.get("problems_frustrations", []):
            topics.append({"topic": f"How to solve {problem}", "type": "Solution"})
        
        # Rule: Interests -> Deep-dive/Insights content
        for interest in insights.get("interests", []):
            topics.append({"topic": f"Deep dive into {interest}", "type": "Insight"})
            
        return topics
