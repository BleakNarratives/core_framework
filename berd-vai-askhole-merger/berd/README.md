# Berd project assets

These Markdown briefs are ordinary project files. They do not automatically create Berd personas or skills and do not modify global Berd data. The product/demo name is **Berdical AI**; it is a local workbench concept, not an official Block or Berd project.

Create a Berd project using the app UI or the bundled `berdctl` while Berd is running:

```bash
~/.local/share/xyz.block.berd/bin/berdctl project create \
  --name "Berdical AI" \
  --instructions "Keep all lead messages as drafts; never contact anyone." \
  --working-dir "$HOME/berd-vai-askhole-merger"
```

You can then use an agent brief as the instructions when creating a persona in Berd, and paste the skill body into Berd's skill creator. Read the source and its permissions first. Keep the project folder attached; do not attach the whole home directory.

Project agent briefs:

- `agents/research-scout.md`
- `agents/askhole-drafter.md`
- `agents/hostile-reviewer.md`
- `agents/compliance-editor.md`

Project skill briefs:

- `skills/lead-to-reviewed-draft/SKILL.md`
- `skills/legacy-context-audit/SKILL.md`
