const state = {
  token: "",
  health: null,
  report: null,
  proposal: null,
  proposalPath: "",
  pollTimer: null,
  verifyInFlight: false,
};

const byId = (id) => document.getElementById(id);
const ui = {
  connection: byId("connection-pill"),
  operationLabel: byId("operation-label"),
  operationDetail: byId("operation-detail"),
  scope: byId("scope"),
  requireComplete: byId("require-complete"),
  autoMonitor: byId("auto-monitor"),
  pollInterval: byId("poll-interval"),
  verifyButton: byId("verify-button"),
  metricFiles: byId("metric-files"),
  metricReceipts: byId("metric-receipts"),
  metricErrors: byId("metric-errors"),
  metricWarnings: byId("metric-warnings"),
  verdict: byId("verdict-badge"),
  findings: byId("findings-body"),
  workspace: byId("capability-workspace"),
  writeCapability: byId("capability-write"),
  signingCapability: byId("capability-signing"),
  events: byId("event-stream"),
  clearEvents: byId("clear-events"),
  writeLock: byId("write-lock"),
  form: byId("proposal-form"),
  previewButton: byId("preview-button"),
  stampButton: byId("stamp-button"),
  proposalPath: byId("proposal-path"),
  proposalJson: byId("proposal-json"),
  confirmation: byId("confirmation"),
  confirmationHelp: byId("confirmation-help"),
  requireSigned: byId("require-signed"),
  themeToggle: byId("theme-toggle"),
};

function setOperation(label, detail, tone = "neutral") {
  ui.operationLabel.textContent = label;
  ui.operationDetail.textContent = detail;
  ui.operationLabel.dataset.tone = tone;
}

function setConnection(mode, label) {
  ui.connection.className = `status-pill ${mode}`;
  ui.connection.textContent = label;
}

function formatTime(value = new Date()) {
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(value);
}

function logEvent(message, tone = "info") {
  const item = document.createElement("li");
  item.dataset.tone = tone;
  const time = document.createElement("time");
  time.dateTime = new Date().toISOString();
  time.textContent = formatTime();
  item.append(time, document.createTextNode(` ${message}`));
  ui.events.prepend(item);
  while (ui.events.children.length > 80) {
    ui.events.lastElementChild.remove();
  }
}

async function api(path, body, mutation = false) {
  const options = body === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
  if (mutation) {
    options.headers = { ...(options.headers || {}), "X-Bufftag-Token": state.token };
  }
  const response = await fetch(path, {
    ...options,
    cache: "no-store",
    credentials: "same-origin",
  });
  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new Error(`API returned non-JSON HTTP ${response.status}`);
  }
  if (!response.ok || payload.ok === false) {
    const error = new Error(payload?.error?.message || `API request failed (${response.status})`);
    error.code = payload?.error?.code;
    error.status = response.status;
    throw error;
  }
  return payload;
}

function renderReport(report) {
  state.report = report;
  const findings = Array.isArray(report.findings) ? report.findings : [];
  const errors = findings.filter((finding) => finding.severity === "error").length;
  const warnings = findings.filter((finding) => finding.severity === "warn").length;

  ui.metricFiles.textContent = String(report.files_scanned ?? "—");
  ui.metricReceipts.textContent = String(report.receipt_count ?? "—");
  ui.metricErrors.textContent = String(errors);
  ui.metricWarnings.textContent = String(warnings);
  ui.verdict.className = `verdict ${report.ok ? "pass" : "fail"}`;
  ui.verdict.textContent = report.ok ? "NO ERRORS" : "FAILED";

  const rows = findings.length
    ? [...findings].sort((left, right) => {
        const rank = { error: 0, warn: 1 };
        return (rank[left.severity] ?? 2) - (rank[right.severity] ?? 2);
      })
    : [];

  ui.findings.replaceChildren();
  if (rows.length === 0) {
    const row = document.createElement("tr");
    row.className = "empty-row";
    const cell = document.createElement("td");
    cell.colSpan = 4;
    cell.textContent = "Live verification returned no findings for this scope.";
    row.append(cell);
    ui.findings.append(row);
    return;
  }

  for (const finding of rows) {
    const row = document.createElement("tr");
    const severity = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = `severity ${finding.severity}`;
    badge.textContent = finding.severity.toUpperCase();
    severity.append(badge);
    const code = document.createElement("td");
    code.textContent = finding.code;
    const path = document.createElement("td");
    path.textContent = finding.path;
    const message = document.createElement("td");
    message.textContent = finding.message;
    row.append(severity, code, path, message);
    ui.findings.append(row);
  }
}

function expectedConfirmation() {
  const file = ui.form.elements.file.value.trim();
  return file ? `STAMP ${file}` : "";
}

function resetProposal(message = "Preview writes nothing. Origin and author remain unverified until you declare them.") {
  state.proposal = null;
  state.proposalPath = "";
  ui.proposalPath.textContent = "NO FILE SELECTED";
  ui.proposalJson.textContent = message;
  ui.confirmation.value = "";
  updateWriteGate();
}

function updateWriteGate() {
  const writesEnabled = Boolean(state.health?.allow_write);
  const signatureAvailable = state.health?.signing?.mode === "hmac-sha256";
  const file = ui.form.elements.file.value.trim();
  const expected = expectedConfirmation();
  const proposalCurrent = Boolean(state.proposal && state.proposalPath === file);
  const signedRequestPossible = !ui.requireSigned.checked || signatureAvailable;
  const confirmed = ui.confirmation.value === expected;
  const enabled = writesEnabled && proposalCurrent && signedRequestPossible && confirmed;

  ui.stampButton.disabled = !enabled;
  ui.writeLock.className = `write-lock ${writesEnabled ? "enabled" : ""}`;
  ui.writeLock.textContent = writesEnabled ? "WRITE GATE ARMED" : "READ ONLY";
  ui.confirmation.placeholder = expected || "STAMP path/to/file.py";

  if (!writesEnabled) {
    ui.confirmationHelp.textContent = "Server is read-only. Restart with --allow-write to enable this mutation.";
  } else if (!proposalCurrent) {
    ui.confirmationHelp.textContent = "Generate a proposal for the current file before writing.";
  } else if (!signedRequestPossible) {
    ui.confirmationHelp.textContent = "Signed mode was requested, but the server has no configured HMAC key.";
  } else {
    ui.confirmationHelp.textContent = `Type the exact phrase: ${expected}`;
  }
}

async function runVerification({ quiet = false } = {}) {
  if (state.verifyInFlight) return;
  if (!state.token) return;
  state.verifyInFlight = true;
  ui.verifyButton.disabled = true;
  if (!quiet) setOperation("VERIFYING LIVE SCOPE", `Scanning ${ui.scope.value || "."} through the local API.`, "busy");
  try {
    const payload = await api("/api/verify", {
      root: ui.scope.value.trim() || ".",
      require_complete: ui.requireComplete.checked,
    }, true);
    renderReport(payload.report);
    setOperation(
      payload.report.ok ? "LIVE SCOPE VERIFIED" : "LIVE SCOPE HAS ERRORS",
      `${payload.report.files_scanned} files · ${payload.report.receipt_count} receipts · scope ${ui.scope.value || "."}`,
      payload.report.ok ? "pass" : "fail",
    );
    if (!quiet) logEvent(`verify ${payload.report.ok ? "passed" : "failed"} with ${payload.report.findings.length} findings`, payload.report.ok ? "pass" : "error");
  } catch (error) {
    setOperation("VERIFICATION API ERROR", error.message, "error");
    if (!quiet) logEvent(`verify error: ${error.message}`, "error");
  } finally {
    state.verifyInFlight = false;
    ui.verifyButton.disabled = false;
  }
}

function restartPolling() {
  if (state.pollTimer !== null) {
    window.clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
  if (!ui.autoMonitor.checked || !state.token) return;
  const interval = Number(ui.pollInterval.value) * 1000;
  state.pollTimer = window.setInterval(() => {
    if (!document.hidden) runVerification({ quiet: true });
  }, interval);
}

async function generateProposal(event) {
  event.preventDefault();
  const data = new FormData(ui.form);
  const file = String(data.get("file") || "").trim();
  if (!file) return;
  ui.previewButton.disabled = true;
  setOperation("GENERATING UNTRUSTED PROPOSAL", "No filesystem writes are performed by proposal generation.", "busy");
  try {
    const payload = await api("/api/propose", {
      root: ui.scope.value.trim() || ".",
      file,
    }, true);
    state.proposal = payload.proposal;
    state.proposalPath = payload.proposal.path;
    ui.proposalPath.textContent = payload.proposal.path;
    ui.proposalJson.textContent = JSON.stringify(payload.proposal, null, 2);
    ui.form.elements.pillar.value = payload.proposal.metadata.pillar;
    ui.form.elements.role.value = payload.proposal.metadata.role;
    ui.form.elements.deps.value = payload.proposal.metadata.deps;
    ui.confirmation.value = "";
    updateWriteGate();
    setOperation("PROPOSAL READY", "Review warnings and declare origin/author before confirming.", "neutral");
    logEvent(`proposal generated for ${payload.proposal.path}; no writes`, "info");
  } catch (error) {
    resetProposal(`Proposal failed: ${error.message}`);
    setOperation("PROPOSAL API ERROR", error.message, "error");
    logEvent(`proposal error: ${error.message}`, "error");
  } finally {
    ui.previewButton.disabled = false;
  }
}

async function stampFile() {
  const file = ui.form.elements.file.value.trim();
  const expected = expectedConfirmation();
  if (!state.proposal || state.proposalPath !== file || ui.confirmation.value !== expected) {
    updateWriteGate();
    return;
  }
  const data = new FormData(ui.form);
  ui.stampButton.disabled = true;
  setOperation("STAMPING FILE", "Atomic content write and receipt append are in progress.", "busy");
  try {
    const payload = await api("/api/stamp", {
      root: ui.scope.value.trim() || ".",
      file,
      origin: String(data.get("origin") || "").trim(),
      pillar: String(data.get("pillar") || "").trim(),
      role: String(data.get("role") || "").trim(),
      author: String(data.get("author") || "").trim(),
      deps: String(data.get("deps") || "none").trim() || "none",
      recorded_at: new Date().toISOString(),
      require_signed: ui.requireSigned.checked,
      confirmation: ui.confirmation.value,
    }, true);
    const receiptId = payload.result?.receipt?.record_id || "unknown";
    logEvent(`stamped ${file}; receipt ${receiptId}`, "pass");
    resetProposal("Stamp completed. Generate a new proposal before another mutation.");
    await runVerification({ quiet: true });
  } catch (error) {
    setOperation("STAMP REJECTED", error.message, "error");
    logEvent(`stamp rejected: ${error.message}`, "error");
    updateWriteGate();
  }
}

function renderHealth(health) {
  state.health = health;
  state.token = health.api_token;
  ui.workspace.textContent = health.workspace;
  ui.writeCapability.textContent = health.allow_write ? "ENABLED — exact confirmation required" : "DISABLED — read only";
  ui.signingCapability.textContent = health.signing.mode === "hmac-sha256"
    ? `HMAC-SHA256 via ${health.signing.environment}`
    : "UNSIGNED receipts";
  ui.requireSigned.checked = health.signing.mode === "hmac-sha256";
  ui.requireSigned.disabled = health.signing.mode !== "hmac-sha256";
  setConnection("online", "LOCAL API ONLINE");
  updateWriteGate();
}

async function boot() {
  const savedTheme = window.localStorage.getItem("bufftag-theme");
  const preferredLight = window.matchMedia("(prefers-color-scheme: light)").matches;
  document.documentElement.dataset.theme = savedTheme || (preferredLight ? "light" : "dark");
  resetProposal();
  ui.clearEvents.addEventListener("click", () => ui.events.replaceChildren());
  ui.themeToggle.addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
    document.documentElement.dataset.theme = next;
    window.localStorage.setItem("bufftag-theme", next);
  });
  ui.verifyButton.addEventListener("click", () => runVerification());
  ui.autoMonitor.addEventListener("change", restartPolling);
  ui.pollInterval.addEventListener("change", restartPolling);
  ui.scope.addEventListener("change", () => {
    resetProposal("Scope changed. Generate a fresh proposal for this scope.");
    runVerification({ quiet: true });
  });
  ui.requireComplete.addEventListener("change", () => runVerification({ quiet: true }));
  ui.form.elements.file.addEventListener("input", () => {
    if (state.proposalPath && state.proposalPath !== ui.form.elements.file.value.trim()) {
      resetProposal("File path changed. Generate a fresh proposal before writing.");
    }
    updateWriteGate();
  });
  ui.form.addEventListener("submit", generateProposal);
  ui.confirmation.addEventListener("input", updateWriteGate);
  ui.requireSigned.addEventListener("change", updateWriteGate);
  ui.stampButton.addEventListener("click", stampFile);

  try {
    const health = await api("/api/health");
    renderHealth(health);
    logEvent(`API handshake complete; writes ${health.allow_write ? "enabled" : "disabled"}; receipts ${health.signing.mode}`, "pass");
    await runVerification();
    restartPolling();
  } catch (error) {
    setConnection("offline", "LOCAL API OFFLINE");
    setOperation("LOCAL API UNAVAILABLE", error.message, "error");
    logEvent(`boot failed: ${error.message}`, "error");
  }
}

boot();
