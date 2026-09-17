
# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: monetization
# DEPS: none
# ROLE: Scrape Hacker News for monetization leads
# AUTHOR: Bleak
# SESSION: 2026-09-11
# TIER: 4
# [/DNA_TAG]

import urllib.request
import json
import time
from pathlib import Path

# Next to this file, not next to the shell's cwd. As a bare "LEADS.md" this wrote
# wherever you happened to be standing, so a cron job or a run from / left a
# stray lead file in the wrong directory. Fixed 2026-09-17 to match
# monitor_leads, which already resolved its own path.
LEADS_FILE = Path(__file__).resolve().parent / "LEADS.md"

# WHAT THIS CAN AND CANNOT PRODUCE
# HN "Show HN" posts are other people's launches -- competitors, not buyers. This
# writes no Matched and no Contact field, so outreach_agent correctly refuses
# every entry it produces with "not a hiring post". That is the honest outcome
# rather than a bug: to get leads out of HN the source would have to be a hiring
# thread, not a launch.
#
# The Algolia endpoint is not rate-limited the way Reddit's RSS is, which makes it
# the one source here that reliably answers -- it is just answering the wrong
# question.

# Query HN for real-time posts mentioning AI debt, broken codebases, or triage
QUERY_URL = "https://hn.algolia.com/api/v1/search_by_date?tags=story&query=agent%20OR%20codebase%20OR%20hallucination%20OR%20%22technical%20debt%22"

def main():
    print("[*] Fetching live Hacker News threads via Algolia API...")
    
    req = urllib.request.Request(
        QUERY_URL,
        headers={'User-Agent': 'ConstraintOps-Monitor/1.0'}
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
            hits = data.get('hits', [])
            
            if not hits:
                print("[-] No hits returned.")
                return

            print(f"[+] Retrieved {len(hits)} raw items from HN API.")
            
            with open(LEADS_FILE, "a") as f:
                f.write(f"\n\n## HN Real-Time Leads ({time.strftime('%Y-%m-%d %H:%M:%S')})\n\n")
                for item in hits[:10]:
                    title = item.get('title', 'No Title')
                    url = item.get('url') or f"https://news.ycombinator.com/item?id={item.get('objectID')}"
                    author = item.get('author', 'unknown')
                    f.write(f"* **[{author}]** {title}\n  - Link: {url}\n")
                    
            print(f"[+] Wrote top 10 live threads to {LEADS_FILE}.")

    except Exception as e:
        print(f"[-] API Error: {e}")

if __name__ == "__main__":
    main()
