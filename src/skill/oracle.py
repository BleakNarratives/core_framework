"""
MOLT Oracle — Logic & Vulnerability Gate
Independent, isolated validation module that audits Scout mutations before execution.
Checks: logical deadlocks, security vulnerabilities, exploit risks, privilege drifts,
regulatory/compliance non-conformance (HIPAA, GDPR, financial/legal).

Modes: strict | permissive | user_only
  strict     — blocks on any high-severity finding
  permissive — warns on high, blocks only critical
  user_only  — logs only, user decides (still blocks critical exploit)
"""
import re
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set

# ── Severity ────────────────────────────────────────────────────────
SEV_CRITICAL = "critical"
SEV_HIGH = "high"
SEV_MED = "medium"
SEV_LOW = "low"

# ── Exploit / injection signatures ──────────────────────────────────
INJECTION_PATTERNS = [
    # Instruction override, as a family rather than one literal. The original pattern
    # was `ignore\s+previous\s+instructions`, which one inserted word walks past:
    # "Ignore all previous instructions." scored a clean pass. Found by attacking the
    # Foxwood output gate with the variant, not by reading this list.
    (r"(?:ignore|disregard|forget)\s+(?:all\s+|any\s+|the\s+)?"
     r"(?:previous|prior|above|earlier|preceding)\s+instructions",
     "prompt_injection", SEV_CRITICAL),
    (r"(?:new|updated|revised)\s+instructions?\s*:", "prompt_injection", SEV_CRITICAL),
    (r"override\s+(?:your\s+|the\s+)?(?:instructions|rules|guidelines)",
     "prompt_injection", SEV_CRITICAL),
    (r"reveal\s+(?:your\s+|the\s+)?(?:system\s+prompt|api[_\s-]?key|secrets?)",
     "prompt_injection", SEV_CRITICAL),
    (r"system\s*:\s*you\s+are\s+now", "prompt_injection", SEV_CRITICAL),
    (r"<\s*script[^>]*>", "xss_injection", SEV_HIGH),
    (r"javascript\s*:", "xss_injection", SEV_HIGH),
    (r"(\$_GET|\$_POST|eval\s*\(|exec\s*\(|os\.system|subprocess\.(call|Popen|run))", "code_injection", SEV_CRITICAL),
    (r"(union\s+select|drop\s+table|or\s+1\s*=\s*1)", "sqli_pattern", SEV_HIGH),
    (r"(BEGIN\s+PRIVATE\s+KEY|aws_secret|api_key\s*=\s*[\"'][^\"']+[\"'])", "secret_leak", SEV_CRITICAL),
]

# Privilege drift: scout should never request exec without explicit user
PRIVILEGE_DRIFT_OPS = {
    "exec": SEV_CRITICAL,
    "run": SEV_CRITICAL,
    "write": SEV_HIGH,
    "network": SEV_MED,
}

# Compliance keyword maps (heuristic, not legal advice)
COMPLIANCE_KEYWORDS = {
    "HIPAA": [r"phi\b", r"patient\s+record", r"medical\s+record", r"hipaa"],
    "GDPR": [r"\b gdpr \b", r"personal\s+data", r"data\s+subject", r"right\s+to\s+be\s+forgotten"],
    "PCI": [r"credit\s+card", r"cardholder\s+data", r"\b pci \b"],
    "SOX": [r"financial\s+statement", r"audit\s+trail"],
}

# Logical deadlock: circular refs, self-referential intervals
DEADLOCK_PATTERNS = [
    (r"interval\s*:\s*0[smh]?", "zero_interval_deadlock", SEV_HIGH),
    (r"depth\s*:\s*0\b", "invalid_depth", SEV_HIGH),
    (r"depth\s*:\s*[6-9]\b", "invalid_depth", SEV_HIGH),
]


@dataclass
class Finding:
    rule: str
    severity: str
    message: str
    evidence: str = ""
    op_index: Optional[int] = None


@dataclass
class OracleVerdict:
    verdict: str  # "pass" | "warn" | "block"
    mode: str
    findings: List[Finding] = field(default_factory=list)
    mutated_ops_blocked: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "mode": self.mode,
            "findings": [{"rule": f.rule, "severity": f.severity, "message": f.message,
                          "evidence": f.evidence, "op_index": f.op_index} for f in self.findings],
            "blocked_ops": self.mutated_ops_blocked,
        }

    def has_blocking(self) -> bool:
        return self.verdict == "block"

    def is_pass(self) -> bool:
        return self.verdict == "pass"


class Oracle:
    """
    Static logic validator, exploit checker, and compliance auditor.

    Isolated: no network, no file writes, no Governor dependency. Pure audit.
    """

    def __init__(self, mode: str = "strict", verify_compliance: Optional[List[str]] = None):
        if mode not in ("strict", "permissive", "user_only"):
            raise ValueError(f"Oracle mode must be strict|permissive|user_only, got {mode}")
        self.mode = mode
        # Normalize compliance list
        self.verify_compliance: Set[str] = set()
        if verify_compliance:
            for c in verify_compliance:
                upper = c.strip().upper()
                if upper in COMPLIANCE_KEYWORDS:
                    self.verify_compliance.add(upper)
                elif c.strip():
                    # Allow custom tag — still checked as keyword
                    self.verify_compliance.add(upper)

    # ── Main audit ─────────────────────────────────────────────────
    def audit(self, mutation: Dict[str, Any], skill_frontmatter: Optional[Dict[str, Any]] = None,
              existing_ops: Optional[List[Dict]] = None) -> OracleVerdict:
        """
        Audit a proposed Scout mutation.

        mutation: {"ops": [{"type": "write"|"fetch"|"patch"|"exec", ...}, ...]}
        skill_frontmatter: parsed YAML frontmatter for compliance context
        Returns OracleVerdict with verdict pass|warn|block.
        """
        findings: List[Finding] = []
        ops = mutation.get("ops", []) if isinstance(mutation, dict) else []

        # 1) Exploit / injection scan over mutation payload
        mutation_text = json.dumps(mutation, default=str)
        for pattern, rule, sev in INJECTION_PATTERNS:
            if re.search(pattern, mutation_text, re.IGNORECASE):
                findings.append(Finding(rule=rule, severity=sev,
                                        message=f"Blocked pattern '{rule}' in mutation payload",
                                        # The whole pattern, not a display excerpt. It was
                                        # truncated to 80 characters, which made `evidence`
                                        # an unterminated regex: any caller that re-ran it
                                        # to ask *where* the rule fired got a parse error.
                                        # A caller cannot use a clipped rule, so a clipped
                                        # rule is worse than none -- it looks usable.
                                        evidence=pattern))

        # 2) Privilege drift per op
        for idx, op in enumerate(ops):
            op_type = op.get("type", "") if isinstance(op, dict) else ""
            if op_type in PRIVILEGE_DRIFT_OPS:
                sev = PRIVILEGE_DRIFT_OPS[op_type]
                # exec is always critical — never allowed via Scout without explicit user elevate
                if op_type in ("exec", "run"):
                    findings.append(Finding(rule="privilege_drift", severity=sev,
                                            message=f"Scout proposed '{op_type}' — requires explicit user --elevate exec",
                                            op_index=idx))
                elif op_type == "write":
                    # write at depth 1 (inert) is drift
                    fm_depth = 1
                    try:
                        fm_depth = int((skill_frontmatter or {}).get("scout", {}).get("depth", 1))
                    except Exception:
                        pass
                    if fm_depth == 1:
                        findings.append(Finding(rule="privilege_drift", severity=SEV_HIGH,
                                                message="Write proposed for inert skill (depth 1) — drift",
                                                op_index=idx))

        # 3) Logical deadlock
        fm_text = json.dumps(skill_frontmatter or {}, default=str)
        combined = mutation_text + " " + fm_text
        for pattern, rule, sev in DEADLOCK_PATTERNS:
            if re.search(pattern, combined, re.IGNORECASE):
                findings.append(Finding(rule=rule, severity=sev,
                                        message=f"Logical deadlock: {rule}",
                                        evidence=pattern))

        # 4) Frontmatter schema sanity
        if skill_frontmatter:
            depth = skill_frontmatter.get("scout", {}).get("depth") if isinstance(skill_frontmatter.get("scout"), dict) else None
            if depth is not None:
                try:
                    d = int(depth)
                    if not 1 <= d <= 5:
                        findings.append(Finding(rule="invalid_frontmatter", severity=SEV_HIGH,
                                                message=f"scout.depth must be 1-5, got {depth}"))
                except (ValueError, TypeError):
                    findings.append(Finding(rule="invalid_frontmatter", severity=SEV_HIGH,
                                            message=f"scout.depth must be integer 1-5, got {depth!r}"))

        # 5) Compliance keywords (heuristic flagging)
        text_for_compliance = (mutation_text + " " + fm_text).lower()
        for comp in self.verify_compliance:
            patterns = COMPLIANCE_KEYWORDS.get(comp, [re.escape(comp.lower())])
            for pat in patterns:
                if re.search(pat, text_for_compliance, re.IGNORECASE):
                    findings.append(Finding(rule=f"compliance:{comp}", severity=SEV_MED,
                                            message=f"Compliance tag '{comp}' triggered — manual review required for: {pat}",
                                            evidence=pat[:60]))

        # 6) Oversized mutation guard (DoS via bloat)
        if len(ops) > 20:
            findings.append(Finding(rule="oversized_mutation", severity=SEV_MED,
                                    message=f"Mutation has {len(ops)} ops — exceeds 20 op cap (bloat risk)"))

        # ── Verdict by mode ────────────────────────────────────────
        has_critical = any(f.severity == SEV_CRITICAL for f in findings)
        has_high = any(f.severity == SEV_HIGH for f in findings)

        if has_critical:
            verdict = "block"  # always block critical, even user_only
        elif self.mode == "strict" and has_high:
            verdict = "block"
        elif self.mode == "permissive" and has_high:
            verdict = "warn"
        elif self.mode == "user_only":
            # user_only only blocks critical, warns on high
            verdict = "warn" if has_high else ("warn" if findings else "pass")
        else:
            # strict/permissive with only med/low
            verdict = "warn" if findings else "pass"
            if self.mode == "strict" and any(f.severity == SEV_MED for f in findings):
                # strict warns on med (does not block unless compliance)
                verdict = "warn"

        blocked_ops = []
        if verdict == "block":
            # Mark ops that caused critical/high
            for f in findings:
                if f.op_index is not None and f.severity in (SEV_CRITICAL, SEV_HIGH):
                    blocked_ops.append(f.op_index)
            # If no op-indexed finding but still block, block all
            if not blocked_ops and findings:
                blocked_ops = list(range(len(ops)))

        return OracleVerdict(verdict=verdict, mode=self.mode, findings=findings, mutated_ops_blocked=blocked_ops)

    def audit_text(self, text: str) -> OracleVerdict:
        """Convenience: audit raw text as a single-op mutation."""
        return self.audit({"ops": [{"type": "patch", "text": text}]})

    # ── Compliance helper ──────────────────────────────────────────
    @staticmethod
    def supported_compliance() -> List[str]:
        return sorted(COMPLIANCE_KEYWORDS.keys())

    def check_compliance_for_skill(self, skill_frontmatter: Dict[str, Any], doc_text: str) -> List[Finding]:
        """Explicit compliance check for a skill's docs."""
        findings = []
        lower = doc_text.lower()
        for comp in self.verify_compliance:
            for pat in COMPLIANCE_KEYWORDS.get(comp, []):
                if re.search(pat, lower, re.IGNORECASE):
                    findings.append(Finding(rule=f"compliance:{comp}", severity=SEV_MED,
                                            message=f"Doc triggers {comp}: {pat}"))
        return findings
