# herald

Find people who are hiring, keep the ones you can actually reply to, and draft
the first message for each.

Named for what it does with *your* words: a herald carries a message, it does not
invent one. That distinction is the whole design, and the reason this project has
no send button.

**Status: working, and idle for want of a source.** Scaffolded 2026-09-17 from
tooling that used to sit loose in the repository root.

## The pipeline

```
            monitor_leads.py                    outreach_agent.py
  feeds ──────────────────────► LEADS.md ──────────────────────────► OUTREACH_DRAFTS.md
  (r/forhire,                 (hiring posts              (one tailored pitch
   r/freelance_forhire)        + contact details)         per contactable lead)
```

Two independent judgements, and they fail separately so you can tell which one is
failing:

1. **Is this someone with paid work?** The subreddit enforces the tag: `[HIRING]`
   means work and a budget. `[FOR HIRE]` means a freelancer advertising
   themselves — the opposite of a lead — and it is excluded *by name*, because a
   loose `hiring` substring would happily admit
   `[FOR HIRE] Senior dev, open to hiring managers`.
2. **Can they be reached?** Emails, external links and an explicit "DM me" are
   recorded; Reddit permalinks are not, because the permalink is already on the
   entry. Posts with no contact detail are skipped and say so.

## Why there is no send mode

`outreach_agent.py` writes `OUTREACH_DRAFTS.md` and stops. Three reasons, shortest
first:

- **There would be nothing to send.** Most posts publish no address, so the route
  is a DM — which needs an authenticated session, not a mail server.
- **It would burn the only asset.** Bulk promotional DMs are what Reddit's terms
  call spam, and the penalty is the account, which is also the lead source.
- **It cannot write the pitch.** The tool can find who is hiring; it cannot know
  what you sell. So `--about` is required, and the model is allowed to reply
  "NO FIT" — which it does, unprompted, when the offer does not match the post.

What you get instead is one click: each draft carries a `mailto:` with the subject
and body prefilled. The machine writes the copy; you press send, from your
identity, having read it.

## Files

| File | What |
|---|---|
| `monitor_leads.py` | Feeds → `LEADS.md`. stdlib only, offline-testable filter, `--dry-run` |
| `outreach_agent.py` | `LEADS.md` → `OUTREACH_DRAFTS.md`. Drafts only; no send path exists |
| `hn_leads.py` | HN launches via the Algolia API. Produces no contactable leads — see its header |
| `LEADS.md` | Data, local. Append-only, deduped by URL |
| `OUTREACH_DRAFTS.md` | Data, local. Generated; nothing in it has been sent |

`LEADS.md` and `OUTREACH_DRAFTS.md` are **deliberately not tracked**: they
accumulate other people's contact details, and a repository is not the right place
for a list of strangers' emails. The code is tracked; the people are not.

## Use

```bash
python3 monitor_leads.py --dry-run          # see what would be added
python3 monitor_leads.py                    # append it

python3 outreach_agent.py --list            # who qualifies, and who does not
python3 outreach_agent.py --about FILE      # draft for everyone contactable
```

`outreach_agent.py` calls `bin/ai` — the repository's single model interface —
rather than carrying its own HTTP client. It finds that binary by walking up from
its own directory, because this project has already moved once.

## Known state, 2026-09-17

- **Reddit is returning HTTP 429 for every feed**, in both orders and after a 30s
  wait, so the live path is unverified against Reddit. The filter and the contact
  extraction are verified offline and against fixtures; real feed parsing was
  confirmed working on 2026-09-16 before the rate limit closed in.
- **`LEADS.md` contains zero qualified leads.** Its seven entries predate the
  hiring filter: five discussion threads and two HN competitor launches. Nothing
  in it is a buyer, and `outreach_agent --list` says so entry by entry rather than
  reporting a bare zero.
