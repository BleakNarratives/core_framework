# Global Binaries & PATHs
# Canonical CLI directories are prepended once; command-specific canonical
# wrappers remain responsible for vault loading and target resolution.
case ":${PATH:-}:" in
  *":$HOME/.local/bin:"*) ;;
  *) PATH="$HOME/.local/bin:${PATH:-}" ;;
esac
case ":${PATH:-}:" in
  *":$HOME/.npm-global/bin:"*) ;;
  *) PATH="$HOME/.npm-global/bin:${PATH:-}" ;;
esac
export PATH

# Navigation & Directory Shortcuts
alias ll='ls -la'
alias ..='cd ..'
alias ...='cd ../..'

# Git Operations
alias gs='git status'
alias ga='git add .'
alias gc='git commit -m'
alias gl='git log --oneline -n 10'

# Environment & Python
alias venv='source venv/bin/activate'
alias clip-copy='cat > /mnt/chromeos/shared/MyFiles/clipboard.txt'
alias clip-paste='cat /mnt/chromeos/shared/MyFiles/clipboard.txt'
export MERKABA_HOME="${HOME}/Merkaba"
alias ka_gen="python3 ${HOME}/Merkaba/ka_gen.py"

# The-Werkz Aliases
alias kindred='python3 /home/bleaknarratives/Kindred/kindred_cli.py'
alias boardroom='python3 /home/bleaknarratives/The-Werkz/Official-Vertical-AI-Boardroom/vertical_ai.py'
alias vault='nano /home/bleaknarratives/The-Werkz/.env.vault'

# === Vault/Concierge/Valet System (2026-08-30) ===
alias kv='~/bin/kilo-valet'                          # Kilo via vault
alias kvrun='~/bin/kilo-valet run'                   # Kilo headless run
alias kvserve='~/bin/kilo-valet serve'               # Kilo headless server
alias vload='source ~/bin/vault-env'                 # Load vault keys into shell
alias vlist='python3 ~/valet_concierge_system/concierge.py list'  # List vault keys
alias vget='python3 ~/valet_concierge_system/concierge.py get'    # Get a key: vget openrouter
alias vingest='python3 ~/bin/vault_ingest.py'        # Ingest key txt files into vault
alias vlama='~/bin/llama-serve.sh'                   # llama-server control

# === Tribunal — Truth by Receipt (2026-09-05) ===
alias tribunal-one='~/Tribunal/one-shot.sh'           # Full daemon suite: start/run/stop/status
alias tribunal='python3 ~/tribunal/tribunal_cli.py'   # Unified CLI (deduped 2026-09-11 — was double-defined)
alias tribunal-run='~/Tribunal/go.sh'                 # Wrap a CLI agent + watch + flag
alias tribunal-start='~/Tribunal/one-shot.sh start'   # Start background daemon
alias tribunal-stop='~/Tribunal/one-shot.sh stop'     # Stop background daemon
alias tribunal-status='~/Tribunal/one-shot.sh status' # Check daemon status
alias tribunal-logs='~/Tribunal/one-shot.sh logs'     # Tail daemon output
alias tribunal-help='~/Tribunal/one-shot.sh help'     # Show all options

# === Tribunal Unified CLI (bare `tribunal` defined above, deduped 2026-09-11) ===
alias judo='~/bin/codejudo'                # vault-wrapped Code Judo Dojo (pool rotation)

# Poop shits
alias rme='ls -a && cat README.md'
alias rere='reset && echo "Dumbass lolol" && ls'
alias proj='cd ~/projects && ls -a -U'
alias yessir='source ~/.bashrc'
alias rc='nano ~/.bashrc'
alias aliases='nano ~/.bash_aliases'

# === BULL — filesystem enforcer (built later, alias waits here) ===
alias bull='python3 ${HOME}/BULL.py'

# === DNA tagger — direct to canonical, no wormhole warning ===
alias dna_tag='python3 ${HOME}/tools/provenance/dna_tag.py'

# === DNA provenance watcher — silent on cd (watch auto, stamp manual) ===
# Crostini penguin sources .bash_aliases on new shell. One-line nudge only
# when pwd has untagged .py files. Never stamps without you. Silent when clean.
__dna_watch() {
  [[ "$PWD" == "${_DNA_LAST_PWD:-}" ]] && return 0
  _DNA_LAST_PWD="$PWD"
  local n
  n=$(python3 -c "from pathlib import Path; p=Path('.'); print(sum(1 for f in p.glob('*.py') if f.is_file() and '[DNA_TAG]' not in f.read_text(errors='ignore')))" 2>/dev/null)
  if [[ -n "$n" && "$n" != "0" ]]; then
    echo "🧬 $PWD — $n untagged .py (run: dna_tag --scan-dir .)"
  fi
}
# PROMPT_COMMAND fires on every interactive prompt; _DNA_LAST_PWD dedupes to cd-only
if [[ "${PROMPT_COMMAND:-}" != *"__dna_watch"* ]]; then
  PROMPT_COMMAND='__dna_watch;'"${PROMPT_COMMAND:-}"
fi

# === Crostini penguin: RC tail moved here (2026-09-09) ===
# ChromeOS crosh -> penguin new shells reliably source ~/.bash_aliases
# but not always ~/.bashrc tail, so all interactive customizations live here.

# NVM + Cargo + custom PATHs (idempotent)
if [[ -z "${NVM_DIR:-}" ]]; then
  export NVM_DIR="$HOME/.config/nvm"
fi
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"
[ -f "$HOME/.cargo/env" ] && . "$HOME/.cargo/env"
for _cli_dir in "$HOME/RootBase/bin" "$HOME/.local/bin" "$HOME/.headless-cli/bin" "$HOME/.supercode/bin" "$HOME/.grok/bin" "$HOME/.npm-global/bin"; do
  case ":${PATH:-}:" in
    *":${_cli_dir}:"*) ;;
    *) PATH="${_cli_dir}:${PATH:-}" ;;
  esac
done
export PATH
unset _cli_dir
[[ -r "$HOME/.grok/completions/bash/grok.bash" ]] && source "$HOME/.grok/completions/bash/grok.bash"

# Charge hook (single definition, was duplicated in RC)
charge() { if [ "$1" = "69" ]; then ~/bin/orchestrate egg; fi; ~/bin/master_control.sh charge "$@"; }

# py helper — py <script[.py]> [args...]
py() {
    if [[ -z "$1" ]]; then
        echo "Usage: py <script[.py]> [args...]"
        return 1
    fi
    local script="$1"
    shift
    if [[ "$script" != *.py ]]; then
        script="${script}.py"
    fi
    python3 "$script" "$@"
}

# Vault/Concierge Lazy Susan trapdoor (moved from RC)
if [ -f "$HOME/bin/vault_toggle" ]; then
  . "$HOME/bin/vault_toggle"
fi

# Freebuff doctor OPT-IN (disabled by default — see RC history)
if [ -z "$FREEBUFF_DOCTOR_SPAWNED" ] && [ "$FREEBUFF_DOCTOR_AUTOSPAWN" = "1" ] \
   && [ -x "$HOME/bin/freebuff_doctor.sh" ] \
   && [ "$(cut -d. -f1 /proc/uptime)" -lt 300 ]; then
    export FREEBUFF_DOCTOR_SPAWNED=1
    "$HOME/bin/freebuff_doctor.sh" >/dev/null 2>&1 &
fi

alias python=python3
export NODE_OPTIONS="--max-old-space-size=8192"
alias start_swarm='source /home/bleaknarratives/RootBase/bin/start_swarm_tmux.sh'

# Prompt + terminal (was RC tail)
export PS1='\[\e[1;35m\]☠ Cocaine \& Hookers: The Movie ☠\[\e[0m\] \[\e[36m\]\w\[\e[0m\] $ '
{ tput smam 2>/dev/null || true; tput smam 2>/dev/null || true; }


# === Sherpa — humane curator (durable, Crostini-safe) ===
# Bin already: ~/bin/sherpa, ~/bin/tour, ~/bin/c, ~/bin/where-was-i
# This block makes `cd` whisper and keeps ~/bin in PATH even if .bashrc tail missed
case ":${PATH:-}:" in
  *":$HOME/bin:"*) ;;
  *) PATH="$HOME/bin:${PATH:-}" ;;
esac
export PATH
# whisper after cd — only if folder has .py or CURATOR.md, never writes unless you ask
sherpa_cd_hook_durable() {
  if [[ -f "$HOME/tools/curator/curator.py" && "$PWD" != "$HOME" ]]; then
    if ls *.py >/dev/null 2>&1 || [[ -f CURATOR.md ]]; then
      echo "— sherpa: $(basename "$PWD") — type \`sherpa\` or \`c\` to tour, \`sherpa --write\` to leave memory —"
    fi
  fi
}
if ! type sherpa_cd >/dev/null 2>&1; then
  sherpa_cd() { builtin cd "$@" && sherpa_cd_hook_durable; }
  alias cd='sherpa_cd'
fi
# short aliases stay in terminal, no copy needed
alias c='sherpa'
alias tour='sherpa'

# === Council + fartographer (Codebase Boardroom) — humane, local, state+SIMS ===
# council = the boardroom that SEES your codebase (6 hard cats, cite [E#], burnout-aware sims)
# fartographer = same council, but 💨 — you were right the first time

# === Soft Pillow — gh naps, git (Linus) stays, checkout hell fixed ===
# gh is Microsoft's social layer — bricked softly; `command gh` still works if you need it
# gh copilot has to reach the real gh, so this is a function rather than a plain
# alias: the nap stays the default, and copilot is the one pass-through.
# Without this, `gh copilot` printed the nap message and exited non-zero, so the
# extension was installed but unreachable from an interactive shell.
gh() {
  if [ "$1" = "copilot" ]; then
    command gh "$@"
  else
    echo "💤 gh is napping — soft pillow active. Use: council / sherpa / git go / git back. Wake with: command gh  (gh copilot passes through)" >&2
    return 1
  fi
}
# checkout was 3 tools in 1 — split so you never guess again
git config --global alias.go "switch" 2>/dev/null
git config --global alias.gcb "switch -c" 2>/dev/null
git config --global alias.back "restore" 2>/dev/null
git config --global alias.co "switch" 2>/dev/null
# default branch for *new* repos only — existing stay as they are (main/master/grand whatever)
git config --global init.defaultBranch main 2>/dev/null
# make `git grand` work anywhere: creates/switches to 'grand' without caring what the remote calls it
git config --global alias.grand "!f(){ git switch -c grand 2>/dev/null || git switch grand; }; f" 2>/dev/null

# === Pooper — Mikey 15-min globs: X -> Sherpa for Claude/Gemini app ===
# pooper / poop / glob <id> — one paste, 15 min, no KYC, no bank
# pooper --status / --list / --again / --out ~/glob.md

# === Atlas — Gap Atlas: reproducible market+scale dungeon (seeded deck) ===
# atlas --seed 42  |  atlas --html /tmp/atlas.html --json /tmp/atlas.json  |  atlas --quest 3

# === keys — ONE command for the vault (2026-09-15) ===
# Replaces the pile of near-identical aliases (vload/vget/vlist/vingest +
# `vault_toggle speakeasy`). Those still work; this is the one to remember.
#   keys          show whether live keys are loaded in THIS shell
#   keys on       load live keys into this shell only
#   keys off      scrub them back out
#   keys list     list providers in the vault
#   keys get <p>  print one provider's key
# Self-contained on purpose: it must not depend on vault_toggle having been
# sourced first, or a load-order change silently turns `keys on` into running
# the vault_toggle FILE (which only prints usage) instead of loading keys.
keys() {
  local mode="${1:-status}" var
  case "$mode" in
    on)
      if [ ! -r "$HOME/bin/vault-env" ]; then
        echo "[keys] missing $HOME/bin/vault-env" >&2; return 3
      fi
      . "$HOME/bin/vault-env" >/dev/null 2>&1
      export CONCIERGE_MODE="speakeasy"
      echo "[keys] mode=speakeasy loaded=${_VAULT_LOADED_LIST:-none}"
      ;;
    off)
      for var in $(compgen -v | grep -E '_(API_KEY|API_KEY_POOL|KEY|TOKEN)$'); do
        unset "$var" 2>/dev/null
      done
      export CONCIERGE_MODE="grocery"
      export _VAULT_LOADED_LIST=""
      echo "[keys] mode=grocery (live keys scrubbed from this shell)"
      ;;
    list) python3 "$HOME/valet_concierge_system/concierge.py" list ;;
    get)  shift; python3 "$HOME/valet_concierge_system/concierge.py" get "$@" ;;
    *)    echo "[keys] mode=${CONCIERGE_MODE:-grocery} loaded=${_VAULT_LOADED_LIST:-none}" ;;
  esac
}

# === fix / trace — tracebacks diagnose themselves (2026-09-15) ===
# fix   : hand the LAST traceback you already have to errfix, e.g.
#           python x.py 2>&1 | fix --stdin
#         or just:  fix python x.py
# trace : run a command and ONLY if it fails, auto-diagnose it. On success it
#         behaves like running the command normally (output passes straight
#         through), so wrapping something never changes what you see.
#           trace npm test
#           trace python thing.py
# Disable the auto-diagnosis for one run with ERRFIX_AUTO=0.
alias fix='errfix'
trace() {
  if [ $# -eq 0 ]; then echo "usage: trace <command> [args...]" >&2; return 2; fi
  local log rc
  log="$(mktemp -t errfix.XXXXXX)"
  "$@" 2> >(tee "$log" >&2)
  rc=$?
  if [ $rc -ne 0 ] && [ "${ERRFIX_AUTO:-1}" != 0 ]; then
    if command -v errfix >/dev/null 2>&1; then
      errfix --file "$log" >&2
    fi
  fi
  rm -f "$log"
  return $rc
}

# Launch Gemma model via Ollama
alias gemma='pgrep ollama > /dev/null || (ollama serve & sleep 5); ollama run hf.co/unsloth/gemma-3-4b-it-unsloth-bnb-4bit:Q4_K_XL'
