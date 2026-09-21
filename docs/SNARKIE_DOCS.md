# Snarkie: The Cynical DecisionAuditEngine

Snarkie is a high-signal, self-auditing tool that converts your codebase's architectural decisions into actionable, cynical commentary. Integrated directly into the `SLaSHdotHIDE` visor system, it serves as an automated drill instructor for your code.

## Core Philosophy

"What you see depends on who you are." — Snarkie audits what you *do* based on your current `Instar`/`Snarkie-Level`. It treats code drift and policy violation with brutal cynicism, ensuring you are aligned with project goals defined in `GEMINI.md`.

## The Snarkie-Level Ladder (Instar Integration)

Snarkie’s privilege and cynicism scale with your current `Instar` level:

| Level | Persona | "Get 'Em" Authority |
| :--- | :--- | :--- |
| **1** | Passive-Aggressive | Log only (Writes to `WHO_DID_WHAT.md`) |
| **2** | Sarcastic | Block + TTS Alert |
| **3** | Cynical Auditor | Block + TTS Alert + Local Remediation (Auto-fix) |
| **4** | Drill Instructor | Above + Execute (Run tests, lint, git stash) |
| **5** | Architect | Above + Full System Elevation (Admin actions) |

## Integration with SLaSHdotHIDE

Snarkie hooks into `visor.py`. Every high-privilege action (read, write, exec) is audited by `SnarkieAuditor` before completion. 

- **Policy Auditing**: Decisions are evaluated against project policies in `GEMINI.md`.
- **Enforcement**: If a decision violates policy, Snarkie blocks the action and delivers a brutal critique.

## Getting Started

1.  **Installation**: Ensure `pyperclip` is installed (`pip install pyperclip`).
2.  **Launching**:
    ```bash
    python3 -m src.skill.snark_reader
    ```
3.  **Hailing**: Use the "Get 'Em" signal (command/trigger) to direct Snarkie to perform specific actions on the codebase (e.g., fetching a repo, analyzing imports).

## Security & Governance

- **Audit Logs**: All snarky commentary and triggered actions are recorded in `.SLaSHdotHIDEfiles/WHO_DID_WHAT.md`.
- **Oracle Compliance**: All automated remediations (Levels 3+) are audited by the `Oracle` engine before being applied to the workspace.

*Built to enforce excellence through cynicism.*
