---
description: Propose many ways to build the board and let Lean rate each one
argument-hint: "[number of builds, default 40]"
allowed-tools: Bash(python3 leanvsdfm/tools/explore.py:*), Bash(python3 leanvsdfm/tools/viz.py:*), Read
---
Explore footprint choices for the Sierrathon board. Proposers are untrusted; only the
Lean-certified verdict counts.

1. Run `python3 leanvsdfm/tools/explore.py ${ARGUMENTS:-40} leanvsdfm/explore/results.json`.
2. Summarise: how many builds are green, yellow and red per proposer, and the best certified build.
3. For the red builds, group the reasons (wrong package, courtyard collision, land pattern).
4. If asked for figures, run `python3 leanvsdfm/tools/viz.py leanvsdfm/explore/results.json assets/viz`.
