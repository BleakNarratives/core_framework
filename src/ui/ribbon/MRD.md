# MRD — Ribbon: What Mike MUST Do With His Eyes

No model can verify how a ribbon *looks*. You do.

## Sign-off (meatsuit)

- [ ] Open `src/ui/ribbon/demo.html` in a real browser (file:// works, no server)
- [ ] Ribbon draws smoothly, no jank, respects `prefers-reduced-motion` (turn on reduce-motion in OS and check it goes still)
- [ ] JS path: inspect `<path>` — has `--len` set to measured length, stroke animates; disable JS and confirm CSS fallback still animates
- [ ] Resize the window — ribbon reflows, doesn't clip or jump
- [ ] `python3 src/ui/ribbon/validate.py` still says PASS (bundle + 3 fixtures)

Signed: _________________  Date: __________

Why this is MRD: render + motion + reflow are visual truths. A passing `validate.py` is necessary but not sufficient — your retina is the last gate.
