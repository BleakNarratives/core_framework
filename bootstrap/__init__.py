"""core_framework.bootstrap — session bootstrap layer (CannibalContext).

Parses the low-token operator context, renders the session kickoff menu,
records session history to a JSONL state stream, and emits the compressed
[SYS_INIT] handshake line used as the bridge primitive with external agents.
"""
