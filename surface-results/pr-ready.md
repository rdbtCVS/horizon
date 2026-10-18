**pr_ready** (`tools/pr_ready.py --quick --base eb3789038e3184c98a1459fe638947200217d360` on archlinux, against eb3789038e3184c98a1459fe638947200217d360 at eb3789038, 1 min 45 s)

| Check | Result |
| --- | --- |
| Scope | ⚠️ 180 files, +12549 −3; 12292 lines of code: over 500, split it if it can ship in parts |
| Cargo.lock | ✅ unchanged |
| Public tree | ✅ |
| Python tests | ✅ 236 passed (19 s) |
| rustfmt | ✅ (4 s) |
| clippy | ✅ (24 s) |
| tests: horizon-world | ✅ 162 passed (58 s) |
| tokens.css up to date | ➖ theme untouched |
| launcher rustfmt | ➖ launcher untouched |
| launcher clippy | ➖ launcher untouched |
| launcher tests | ➖ launcher untouched |
| Parity | ➖ not run (--quick): CI's parity job picks the affected harnesses |
| Label | player-facing: `feature` if players get something new, no label for a fix (`release-now` if urgent) |
