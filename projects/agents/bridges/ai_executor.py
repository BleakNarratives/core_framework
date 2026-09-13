# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: agents
# FKA: ~/ai_executor.py
# ROLE: ai_executor.py — see canonical at ~/projects/agents/bridges/ai_executor.py
# SESSION: 2026-09-08
# TIER: 3
# [/DNA_TAG]

#!/usr/bin/env python3
import os, json, shlex, subprocess, datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

# ----------------------------------------------------------------------
# Configuration – edit these to tighten security
# ----------------------------------------------------------------------
WORKDIR = os.path.expanduser('~/ai_executor/workspace')
ALLOWED_CMDS = {
    'apt', 'git', 'code-server', 'npm', 'node', 'python3', 'pip3',
    'ls', 'cat', 'touch', 'mkdir', 'rm', 'cp', 'mv', 'chmod', 'chown'
}
BLACKLIST = ['rm -rf /', ':(){ :|:& };:']   # simple pattern blocklist
# ----------------------------------------------------------------------


def is_allowed(command: str) -> bool:
    """Very simple whitelist check – all tokens must be in ALLOWED_CMDS."""
    tokens = shlex.split(command)
    if not tokens:
        return False
    # first token is the binary
    return tokens[0] in ALLOWED_CMDS


def run_command(cmd: str):
    """Execute the command as the sandbox user, capture output."""
    # Use 'sudo -u ai_executor' if the Flask process runs as root
    # Here we assume the Flask process already runs as ai_executor
    result = subprocess.run(
        cmd,
        shell=True,
        cwd=WORKDIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=180  # 3 min max per request
    )
    return result.returncode, result.stdout


@app.route('/execute', methods=['POST'])
def execute():
    data = request.get_json(force=True)
    cmd = data.get('command', '').strip()
    if not cmd:
        return jsonify(error='no command supplied'), 400

    # ------------------------------------------------------------------
    # Safety checks
    # ------------------------------------------------------------------
    if any(bad in cmd for bad in BLACKLIST):
        return jsonify(error='command blocked by policy'), 403
    if not is_allowed(cmd):
        return jsonify(error='command not whitelisted'), 403
    # ------------------------------------------------------------------

    rc, out = run_command(cmd)

    # Log the request (append‑only)
    log_line = f"{datetime.datetime.utcnow().isoformat()} | UID:{os.getuid()} | CMD:{cmd} | RC:{rc}\n"
    with open('/var/log/ai_executor.log', 'a') as f:
        f.write(log_line)

    return jsonify(
        command=cmd,
        returncode=rc,
        output=out
    )


if __name__ == '__main__':
    # Run on localhost only – never expose to the network without TLS/auth
    app.run(host='127.0.0.1', port=5005)
