# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: agents
# FKA: ~/ai_agent_server.py
# ROLE: ai_agent_server.py — see canonical at ~/projects/agents/bridges/ai_agent_server.py
# SESSION: 2026-09-08
# TIER: 3
# [/DNA_TAG]

#!/usr/bin/env python3
import json, shlex, subprocess, os
from flask import Flask, request, jsonify

app = Flask(__name__)

WORKDIR = os.path.expanduser('~/ai-workspace')
os.makedirs(WORKDIR, exist_ok=True)

def run_as_user(cmd):
    # Run the command as the sandbox user, capture output
    # If you need sudo, prepend "sudo -u ai_executor"
    result = subprocess.run(
        cmd,
        shell=True,
        cwd=WORKDIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=120
    )
    return result.returncode, result.stdout

@app.route('/execute', methods=['POST'])
def execute():
    data = request.get_json()
    cmd = data.get('command')
    if not cmd:
        return jsonify({'error': 'no command supplied'}), 400

    # *** SAFETY CHECKS ***
    # 1. Disallow dangerous built‑ins unless you explicitly whitelist them
    blacklist = ['rm -rf /', ':(){ :|:& };:']  # add more as needed
    if any(bad in cmd for bad in blacklist):
        return jsonify({'error': 'command blocked by policy'}), 403

    # 2. Optionally enforce a whitelist of allowed binaries
    # allowed = {'apt','git','code','npm','python3','node'}
    # if not set(shlex.split(cmd)).issubset(allowed):
    #     return jsonify({'error': 'command not whitelisted'}), 403

    rc, out = run_as_user(cmd)
    return jsonify({
        'command': cmd,
        'returncode': rc,
        'output': out
    })

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5005)
