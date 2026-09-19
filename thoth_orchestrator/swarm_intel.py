# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: thoth
# ROLE: Undocumented module
# TIER: Scout (6)
# AUTHOR: BleakNarratives
# SESSION: 2026-08-22 ShipWreckD OS Builder — auto-tagged by DNA Sweeper
# [/DNA_TAG]

import json
import requests
from duckduckgo_search import DDGS
from pydantic_ai import Agent, RunContext

# Define a super lightweight agent that handles all data formatting
intelligence_agent = Agent(
    'ollama:llama3.2:1b', # Uses the small 1B model you pulled earlier
    system_prompt=(
        "You are an elite corporate intelligence aggregator. "
        "Analyze the provided JSON business structures and search summaries. "
        "Synthesize the findings into a sharp, bulleted briefing. "
        "Highlight compliance risks (CFPB) and general operational context."
    )
)

@intelligence_agent.tool
def check_cfpb_complaints(ctx: RunContext[str], company_name: str) -> str:
    """Queries live data from the Consumer Financial Protection Bureau."""
    url = "https://consumerfinance.gov"
    try:
        # Pulls the 5 most recent live complaints against the business
        response = requests.get(url, params={"search_term": company_name, "size": 5}, timeout=10)
        if response.status_code == 200:
            data = response.json()
            complaints = [
                {
                    "product": c.get("_source", {}).get("product"),
                    "issue": c.get("_source", {}).get("issue"),
                    "state": c.get("_source", {}).get("state"),
                    "narrative": c.get("_source", {}).get("complaint_what_happened", "")[:200]
                }
                for c in data.get("hits", {}).get("hits", [])
            ]
            return json.dumps(complaints, indent=2)
    except Exception as e:
        return f"CFPB Search Failed: {str(e)}"
    return "No recent CFPB complaints found."

@intelligence_agent.tool
def fallback_web_search(ctx: RunContext[str], query: str) -> str:
    """Searches the live web for recent business filings, news, or changes."""
    try:
        with DDGS() as ddgs:
            results = [r for r in ddgs.text(query, max_results=4)]
            return json.dumps(results, indent=2)
    except Exception as e:
        return f"Web search failed: {str(e)}"

# Define the target company to investigate
target_company = "Wells Fargo"
print(f"[*] Booting local model to analyze: {target_company}...")

# Run the agent synchronously 
result = intelligence_agent.run_sync(
    f"Run an immediate compliance and context check on '{target_company}' using all tools."
)

print("\n=== SWARM INTELLIGENCE REPORT ===")
print(result.data)
