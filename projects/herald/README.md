# herald

Find people who are hiring, keep the ones you can actually reply to, and draft
the first message for each.

Named for what it does with *your* words: a herald carries a message, it does not
invent one. That distinction is the whole design, and the reason this project has
no send button.

**Status: working.** Scaffolded 2026-09-17 from tooling that used to sit loose in
the repository root. The local export currently contains 55 matched posts, of
which 35 retain a person-reachable route; Reddit is still rate-limiting this host.

## The pipeline

```
            monitor_leads.py                    outreach_agent.py
  feeds ──────────────────────► LEADS.md ──────────────────────────► OUTREACH_DRAFTS.md
  (HN "Who is hiring?",        (hiring posts              (one tailored pitch
   r/forhire,                  + contact details)         per contactable lead)
   r/freelance_forhire)
```

Two independent judgements, and they fail separately so you can tell which one is
failing:

1. **Is this someone with paid work?** The subreddit enforces the tag: `[HIRING]`
   means work and a budget. `[FOR HIRE]` means a freelancer advertising
   themselves — the opposite of a lead — and it is excluded *by name*, because a
   loose `hiring` substring would happily admit
   `[FOR HIRE] Senior dev, open to hiring managers`.
2. **Can they be reached?** Contact hints are recorded, but only emails, explicit
   "DM me" routes, and profile pages count as person-reachable. Application forms
   and venues remain visible but do not qualify; Reddit permalinks are not contact
   hints because the permalink is already on the entry.

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
| `hn_leads.py` | HN "Who is hiring?" via the Algolia API. The productive source — see its header |
| `ABOUT.md` | The single `--about` paragraph, fed verbatim. One paragraph on purpose |
| `ABOUT_EVIDENCE.md` | The proof for every claim in it, and what the model may not claim |
| `ABOUT_PRODUCT.md` | The product-role variant of the offer, also one paragraph |
| `.herald_state.json` | Local memory: a verdict per lead, so a batch resumes. Gitignored |
| `LEADS.md` | Data, local. Append-only, deduped by source identity (URL, or HN item ID) |
| repository `data/leads/outbound_candidates.json` | Data, local and ignored. Schema-validated export of 55 unique matched posts; contact routes remain classified |
| `OUTREACH_DRAFTS.md` | Data, local. Generated; nothing in it has been sent |

`LEADS.md` and `OUTREACH_DRAFTS.md` are **deliberately not tracked**: they
accumulate other people's contact details, and a repository is not the right place
for a list of strangers' emails. The code is tracked; the people are not.

## Use

```bash
python3 monitor_leads.py --dry-run          # see what would be added
python3 monitor_leads.py                    # append it

python3 outreach_agent.py --list            # who qualifies, and who does not
python3 outreach_agent.py --about "one honest paragraph"   # draft for everyone contactable
python3 outreach_agent.py --about-file ABOUT.md --model groq::openai/gpt-oss-120b
```

`outreach_agent.py` calls `bin/ai` — the repository's single model interface —
rather than carrying its own HTTP client. It finds that binary by walking up from
its own directory, because this project has already moved once.

## Known state, 2026-09-17

- **The HN source works, and it is the one to use.** The September 2026 "Who is
  hiring?" thread returned 403 comments, 263 top-level job posts and 69 publishing
  an email. The local export contains 55 unique matched posts; 35 retain a person-
  reachable route (email, DM, or profile) after reclassifying legacy `link:` hints.
  Reddit still answers HTTP 429 for every feed, so that path is verified only against
  fixtures.
- **A link is a place, not a person — and it no longer counts as contact.** A hint
  counts as reaching a person only if it is an address, an explicit "DM me", or a
  profile on a platform where a person can be messaged. Application forms are
  classified `apply:`; homepages, job documents, and other non-person URLs are
  classified `venue:` and stay visible without qualifying the lead. The rule is
  applied when reading as well as writing, because `LEADS.md` is append-only and
  holds hints made before it existed. The normalized export applies the same
  reclassification rule and uses HN item IDs so query-keyed URLs cannot collapse
  distinct posts.

- **Fit rate, measured on the clean run.** 30 leads, one pinned model, one run
  each, and a third offer was added: the one-line offer drafted 9 and then 6 on a
  repeat run (so the noise is about three leads), `ABOUT.md` drafted 1, and
  `ABOUT_PRODUCT.md` drafted 0. The refusals are mostly
  correct on their face — robotics and hardware, a sales leadership role,
  principal-level, a Ruby/React stack — which puts the bottleneck in the *lead set*,
  not in the offer paragraph.
- **The terms cause the refusals, not the technical content.** The product-role
  variant is the broadest of the three on skill and drafted **nothing** in 30, because
  it states the deal. 13 refusals name full-time employment against "fixed-price,
  bounded pieces", and the words contract or fixed-price appear 29 times in that run.
  Every "Who is hiring?" post is a salaried ad, so an explicit contracting offer is
  refused on sight: *"you only do fixed-price, bounded Python backend pieces, not
  full-time employment"*. Which means the one-liner scores highest partly by **not
  saying what the deal is**, and a rising fit rate is not automatically a better
  pitch. Worth deciding on purpose: aim at contract-friendly sources, or drop the
  terms and settle them in the conversation.
- **All 35 leads are now reached: 7 drafted, 31 answered, 0 unreached.** The pass took
  four batches and a model switch. Groq's free tier failed 23 calls across two of
  them while absorbing 75 retries, leaving **11 distinct leads** unreached; the same
  remainder then ran
  clean on `openrouter::nvidia/nemotron-3-super-120b-a12b:free` with **zero** retries
  and 3 drafts. That is the practical case for a fallback model rather than more
  patience: the ceiling was the constraint, not the retrying.
- **The state records the verdict, not which model or offer produced it.** A pass
  assembled from more than one model, like the one above, is therefore not
  reproducible from the file alone. Recorded as a known limit rather than papered
  over.
- **Batching resumes now, and it did not before.** A refusal used to go unrecorded, so
  `todo` only excludes leads already *drafted* and the next `--limit` batch restarts
  from the first unrefused lead. Three batches of 15/17/10 made **42 calls covering
  19 distinct leads**, and 16 were never reached at all — it looks like progress and
  is partly repetition. Verdicts now go in
  `.herald_state.json`, so batches advance. `--redo` ignores the memory, and a
  transport failure is deliberately *not* recorded as answered, so a lead lost to a
  429 is retried next time. The memory is per **lead**, not per offer: change the
  `--about` paragraph and you must pass `--redo`, or the old answers stand in for the
  new ones. That matters here, because the offers differ by 9 leads to none.
- **A reply is checked before it is written.** One run returned the *prompt echoed
  back* as its answer, and the tool wrote all of it out as drafts: the drafts file
  went 3.5 KB → 155 KB and the run reported 70% fit. Replies that are not emails
  are now refused, reported in their own category, and a run in which nothing
  usable came back exits non-zero.
- **Pin `--model` before comparing two offers.** The default is `auto`, and at
  least one gateway route returns the prompt verbatim while `auto` mostly does not,
  so two runs of the same code can differ by pool selection rather than content.
- **`ABOUT.md` is one paragraph on purpose.** The 7.4 KB version made the prompt
  ~2,100 tokens against the one-liner's ~300, and Groq's free tier caps at 8,000
  tokens per minute: 8 of 10 calls answered 429 and the run wrote nothing. The file
  is now ~600 tokens and the evidence moved to `ABOUT_EVIDENCE.md`.
- **A rate limit is waited out, not fatal.** A 429 now sleeps for the interval the
  provider itself states and retries, up to 3 times. A 429 caused by an empty
  account is *not* retried, because waiting cannot fix billing — the two look
  identical except for the code inside the message.
- **The shorter offer fits nine times as many leads.** Same 30 leads, one pinned
  model, one run each: the one-line offer drafted **9**, `--about-file ABOUT.md`
  drafted **1**, and all 8 of the difference went one way — the file never fitted a
  lead the one-liner had refused. That is not a defect in `ABOUT.md`: it describes a
  narrow infrastructure offer (coding-agent cost and containment), and most "Who is
  hiring?" posts are product roles, so the model refuses them and is right to.
  A broader offer matches more posts; whether its pitches are as *good* is a
  separate question this cannot measure.
- **The earlier "10% → 70%" reading was an artifact, in the other direction.** Seven
  of those "drafts" were the prompt echoed back, and the drafts file grew from
  3.5 KB to 155 KB. Nothing about it was a fit rate, and it is why replies are now
  validated before they are written (`not_an_email`).
