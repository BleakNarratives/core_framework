# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: agents
# FKA: ~/context_optimizer.py
# ROLE: context_optimizer.py — see canonical at ~/projects/agents/sim/context_optimizer.py
# SESSION: 2026-09-08
# TIER: 3
# [/DNA_TAG]

"""
context_optimizer.py

Anti-drift context pruner for agent execution loops. Prevents the exact
failure mode that killed V's session and the Moto 4 Gemini research loop
tonight: unbounded context growth leading to OOM hangs or stuck loops.

Drop into any agent's execution loop before calling out to a model.
Zero external dependencies.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ContextOptimizer:
    """
    Enforces a hard boundary on conversation history, keeps the active
    task and system intent intact, and truncates oversized tool output
    before it re-enters the context window.
    """

    def __init__(self, max_turn_history: int = 6, keep_system_prompt: bool = True):
        self.max_turn_history = max_turn_history
        self.keep_system_prompt = keep_system_prompt

    def compact(
        self,
        raw_context: List[Dict[str, Any]],
        active_task: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Takes raw context array, returns a hard-bounded context payload."""
        if not raw_context:
            return []

        pruned_payload: List[Dict[str, Any]] = []

        # 1. Preserve system context / anchor intent
        system_nodes = [msg for msg in raw_context if msg.get("role") == "system"]
        if system_nodes and self.keep_system_prompt:
            pruned_payload.extend(system_nodes)

        # 2. Extract and lock active task constraint block
        if active_task:
            task_anchor = {
                "role": "system",
                "content": (
                    f"[ACTIVE_TASK_CONSTRAINT]\n"
                    f"Task: {active_task.get('title', 'Execution')}\n"
                    f"Parameters: {json.dumps(active_task.get('params', {}))}"
                ),
            }
            pruned_payload.append(task_anchor)

        # 3. Truncate conversation turns (rolling window)
        non_system_turns = [msg for msg in raw_context if msg.get("role") != "system"]
        recent_turns = (
            non_system_turns[-self.max_turn_history:]
            if len(non_system_turns) > self.max_turn_history
            else non_system_turns
        )

        # 4. Strip oversized tool payloads from historical turns
        cleaned_turns = []
        for turn in recent_turns:
            cleaned_turn = turn.copy()
            if cleaned_turn.get("role") == "tool" or "tool_calls" in cleaned_turn:
                content_str = str(cleaned_turn.get("content", ""))
                if len(content_str) > 1000:
                    cleaned_turn["content"] = content_str[:1000] + "... [TRUNCATED_TO_PREVENT_DRIFT]"
            cleaned_turns.append(cleaned_turn)

        pruned_payload.extend(cleaned_turns)

        logger.info(
            "Context pruned: original_len=%d, pruned_len=%d",
            len(raw_context), len(pruned_payload),
        )
        return pruned_payload

    def create_checkpoint(self, agent_id: str, full_state: Dict[str, Any]) -> Dict[str, Any]:
        """Minimal checkpoint payload to persist before clearing runtime memory.
        Always stamps its own timestamp — doesn't trust the caller to have one."""
        checkpoint = {
            "agent_id": agent_id,
            "last_active_task": full_state.get("current_task"),
            "core_state": full_state.get("memory_vars", {}),
            "checkpoint_timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._log_prune_event(agent_id)
        return checkpoint

    @staticmethod
    def _log_prune_event(agent_id: str):
        """Leaves the same kind of trace every other substrate action does,
        so Sparks and the card registry can see pruning happened."""
        try:
            with open("WHO_DID_WHAT.md", "a") as f:
                ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                f.write(f"{ts}: ContextOptimizer checkpointed and pruned {agent_id}.\n")
        except FileNotFoundError:
            logger.debug("WHO_DID_WHAT.md not found in cwd — skipping trace log.")


# --- Integration ---
#
# In an agent's execution loop, before any LLM call:
#
#   optimizer = ContextOptimizer(max_turn_history=4)
#   safe_messages = optimizer.compact(raw_history, active_task=current_task)
#
# On tool execution: store raw output to disk/DB, feed only a summary
# back into the context array — don't let a full triage manifest or a
# full diff sit in live context turn after turn.
#
# On session reset (this is what would have saved V and the Moto 4
# session tonight): call create_checkpoint(), flush the context array,
# restart with a clean system prompt plus the checkpoint state instead
# of resuming the bloated history.
