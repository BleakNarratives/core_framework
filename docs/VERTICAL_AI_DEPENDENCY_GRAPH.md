# Vertical AI Dependency Graph

**Generated:** 2026-09-17  
**Mode:** offline; values and credentials excluded.

| Workspace | Python files | Scripts | Imports | Outputs | Environment |
|---|---:|---|---|---|---|
| `vertical_ai` | 3 | scrape_google_reviews.py, automate_outreach.py | __future__, bs4, csv, email, json, pathlib, requests, smtplib, time, typing | businesses_without_websites.csv; local dry-run handoff JSON | CONCIERGE_VAULT |
| `vertical_local` | 11 | app.py, run_boardroom.sh, debate_engine.py | curses, debate_engine, debate_router, dotenv, fastapi, json, openai, os, personas_router, presets_router, providers, pydantic, random, reports, requests, scout_sandbox, subprocess, swarm_client, thoth_client, time, typing, urllib, uuid, uvicorn | web/; data/; temporary service logs and pid files | OPENAI_API_KEY, HF_API_KEY, HOST, PORT |
| `vertical_radar` | 5 | src/radar/main.py | datetime, duckduckgo_search, langchain, langchain_google_genai, langchain_ollama, os, src, time, trafilatura | src/data/report_<client>_<timestamp>.txt | GOOGLE_API_KEY, OLLAMA_HOST |
| `vertical_radar_dupe` | 1 | — | duckduckgo_search, langchain, time, trafilatura | — | — |
| `vertical_ai_engine` | 18 | foia_cli.py | app, argparse, asyncio, collections, config, datetime, google, jinja2, json, logging, modules, os, pytest, random, re, requests, spacy, string, sys, tempfile, tika, unittest, uuid, weasyprint | application logs; processed document storage configured at runtime | GEMINI_API_KEY |

## Verification interpretation

- `PASS`: static metadata/syntax checks completed.
- `SKIP`: live network, provider, vault, SMTP, database, or server behavior intentionally not executed.
- `BLOCKED`: a declared package or source module is absent.
- Secret values are never collected by this generator.
