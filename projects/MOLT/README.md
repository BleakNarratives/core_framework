# MOLT — GitHub distraction copy

This folder is the staged GitHub repo mirror for MOLT (Markdown Originated Living Triad).
Root `README.md` is the canonical GitHub README — copy on publish:

```bash
# when ready to push to github.com/<you>/molt
rm -rf /tmp/molt && mkdir -p /tmp/molt
rsync -a --exclude='.git' --exclude='rag_storage' --exclude='.venv' ./ /tmp/molt/
cp /tmp/molt/projects/MOLT/README.md /tmp/molt/README.md 2>/dev/null || true
# then: gh repo create molt --public --source=/tmp/molt --push
```

Canonical copy lives at `/README.md`. This file exists so `projects/MOLT` is self-contained
for `npx skills add`-style installs later (`--skill molt`).

See also: `projects/MOLT/NAMING.md`, `docs/GAMBIT.md`, `docs/FORCE_MULTIPLIERS.md`.
