#!/usr/bin/env bash
#
# publish.sh — take a package from "verified locally" to "pushed, with a tag".
#
# What this does and does not do is the whole point. It does every mechanical
# step that is safe to automate, refuses to guess anything about your identity,
# and stops at the two commands that need your credentials. It will not create
# a remote, will not push, and will not touch your global git config.
#
#   ./publish.sh check              validate all repos, change nothing
#   ./publish.sh prep <name>        verify, then create the v0.1.0 tag
#   ./publish.sh all                prep every repo
#   ./publish.sh status             one-line summary per repo
#
# Exit 0 only if every repo passed. Any failure is loud.

set -euo pipefail

ROOT="${PUBLISH_ROOT:-$HOME}"
VERSION="${VERSION:-0.1.0}"

# name -> directory
REPOS=(
  "cascade-arbitration:cascade-arbitration-publish"
  "verified-cache:verified-cache"
  "drift-guard:drift-guard"
)

c_red=$'\033[31m'; c_grn=$'\033[32m'; c_yel=$'\033[33m'; c_dim=$'\033[2m'; c_off=$'\033[0m'
[[ -t 1 ]] || { c_red=""; c_grn=""; c_yel=""; c_dim=""; c_off=""; }

fail() { printf '%sFAIL%s  %s\n' "$c_red" "$c_off" "$1"; }
ok()   { printf '%sok%s    %s\n'   "$c_grn" "$c_off" "$1"; }
warn() { printf '%swarn%s  %s\n'   "$c_yel" "$c_off" "$1"; }
note() { printf '%s%s%s\n' "$c_dim" "$1" "$c_off"; }

dir_for() { echo "$ROOT/${1##*:}"; }
name_for() { echo "${1%%:*}"; }

# ── checks ──────────────────────────────────────────────────────────────────

check_repo() {
  local name="$1" dir="$2" problems=0

  printf '\n%s\n' "── $name ${c_dim}($dir)${c_off}"

  if [[ ! -d "$dir/.git" ]]; then
    fail "not a git repository: $dir"; return 1
  fi
  ok "is a git repository"

  # Clean tree. Untracked files count -- a dirty tree means a tag would not
  # describe what is actually on disk.
  if [[ -n "$(git -C "$dir" status --porcelain)" ]]; then
    fail "working tree is dirty:"
    git -C "$dir" status --porcelain | sed 's/^/        /'
    problems=$((problems+1))
  else
    ok "working tree clean"
  fi

  # No generated artefacts committed.
  if git -C "$dir" ls-files | grep -qE '(^|/)(build|dist|__pycache__)(/|$)|\.egg-info/|\.pyc$'; then
    fail "generated files are tracked:"
    git -C "$dir" ls-files | grep -E '(^|/)(build|dist|__pycache__)(/|$)|\.egg-info/|\.pyc$' | sed 's/^/        /'
    problems=$((problems+1))
  else
    ok "no generated files tracked"
  fi

  # Required files.
  local missing=()
  for f in README.md LICENSE pyproject.toml; do
    [[ -f "$dir/$f" ]] || missing+=("$f")
  done
  if ((${#missing[@]})); then
    fail "missing: ${missing[*]}"
    problems=$((problems+1))
  else
    ok "has README, LICENSE, pyproject"
  fi

  # Placeholders that need a human. These are identity decisions.
  if grep -q 'OWNER' "$dir/pyproject.toml" 2>/dev/null; then
    warn "pyproject.toml still has an OWNER placeholder -- set it before publishing"
  fi
  if grep -qE 'Copyright \(c\) [0-9]{4}$' "$dir/LICENSE" 2>/dev/null; then
    warn "LICENSE has no copyright holder -- set it before publishing"
  fi

  # Tests must pass with no install, which is the only guarantee we make.
  if [[ -d "$dir/tests" ]]; then
    :
  fi
  if compgen -G "$dir/test_*.py" >/dev/null; then
    if (cd "$dir" && python3 -m unittest discover -p 'test_*.py' >/tmp/_pt.$$ 2>&1); then
      ok "tests pass ($(grep -oE 'Ran [0-9]+ tests?' /tmp/_pt.$$ | head -1))"
    else
      fail "tests fail:"; sed 's/^/        /' /tmp/_pt.$$ | tail -20; problems=$((problems+1))
    fi
    rm -f /tmp/_pt.$$
  else
    warn "no test_*.py found"
  fi

  # Imports must not pull a heavy dependency into the arbiter/cache paths.
  if grep -qE '^\s*(import|from)\s+(torch|numpy|transformers)' "$dir"/*.py 2>/dev/null; then
    fail "unexpected heavy dependency imported"
    problems=$((problems+1))
  else
    ok "no heavy dependencies"
  fi

  # Remote.
  if git -C "$dir" remote get-url origin >/dev/null 2>&1; then
    ok "remote origin: $(git -C "$dir" remote get-url origin)"
  else
    note "no remote yet -- you will add one"
  fi

  return $(( problems > 0 ? 1 : 0 ))
}

# ── prep ────────────────────────────────────────────────────────────────────

prep_repo() {
  local name="$1" dir="$2"
  printf '\n%s\n' "── prep $name"

  if ! check_repo "$name" "$dir"; then
    fail "not prepped -- fix the above first"; return 1
  fi

  if git -C "$dir" rev-parse "v$VERSION" >/dev/null 2>&1; then
    note "tag v$VERSION already exists"
  elif git -C "$dir" tag -a "v$VERSION" -m "v$VERSION" >/dev/null 2>&1; then
    ok "tagged v$VERSION"
  fi
}

# ── commands ────────────────────────────────────────────────────────────────

next_steps() {
  printf '\n%sNext steps -- these need your credentials, so the script stops here.%s\n\n' "$c_off" "$c_off"
  printf '  1. Fill in the two placeholders flagged above:\n'
  printf '       [project.urls] Issues in each pyproject.toml  (OWNER)\n'
  printf '       the copyright holder line in each LICENSE\n\n'
  printf '  2. Create an empty GitHub repo per package (no README, no .gitignore),\n'
  printf '     then run these verbatim:\n\n'
  local r n d
  for r in "${REPOS[@]}"; do
    n=$(name_for "$r"); d=$(dir_for "$r")
    printf '       # %s\n' "$n"
    printf '       cd %s\n' "$d"
    printf '       git remote add origin git@github.com:<you>/%s.git\n' "$n"
    printf '       git push -u origin main\n'
    printf '       git push origin v%s\n\n' "$VERSION"
  done
  printf '  3. Confirm what a stranger will actually see:\n'
  printf '       git ls-remote --heads origin\n'
  # One printf, two placeholders. Passing two args to a single-%s format makes
  # bash reuse the format and print the line twice.
  printf '\n%sNothing above has been executed. No remote was created, nothing was\npushed, and your global git config was not modified.%s\n' "$c_dim" "$c_off"
}

main() {
  local cmd="${1:-check}"; shift || true
  case "$cmd" in
    check)
      local rc=0
      for r in "${REPOS[@]}"; do
        check_repo "$(name_for "$r")" "$(dir_for "$r")" || rc=1
      done
      printf '\n'
      if ((rc == 0)); then
        printf '%sall checks passed%s\n' "$c_grn" "$c_off"
        next_steps
      else
        printf '%ssome checks failed%s\n' "$c_red" "$c_off"
      fi
      return $rc
      ;;
    status)
      printf '%-24s %-8s %-7s %-7s %s\n' REPO COMMITS TESTS TAG REMOTE
      for r in "${REPOS[@]}"; do
        local n d commits tests tag remote
        n=$(name_for "$r"); d=$(dir_for "$r")
        commits=$(git -C "$d" rev-list --count HEAD 2>/dev/null || echo 0)
        tests=$( (cd "$d" && python3 -m unittest discover -p 'test_*.py' 2>&1 | grep -oE 'Ran [0-9]+' | grep -oE '[0-9]+') || echo "-")
        tag=$(git -C "$d" tag --list 'v*' 2>/dev/null | head -1); tag=${tag:--}
        remote=$(git -C "$d" remote get-url origin 2>/dev/null || echo "-")
        printf '%-24s %-8s %-7s %-7s %s\n' "$n" "$commits" "${tests:-?}" "$tag" "$remote"
      done
      ;;
    prep)
      if (($# == 0)); then
        for r in "${REPOS[@]}"; do prep_repo "$(name_for "$r")" "$(dir_for "$r")"; done
      else
        for r in "${REPOS[@]}"; do
          [[ "$(name_for "$r")" == "$1" ]] && { prep_repo "$(name_for "$r")" "$(dir_for "$r")"; exit $?; }
        done
        fail "unknown repo: $1"; exit 1
      fi
      ;;
    all)
      for r in "${REPOS[@]}"; do prep_repo "$(name_for "$r")" "$(dir_for "$r")"; done
      ;;
    *)
      sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'
      exit 1
      ;;
  esac
}

main "$@"
