# Constant surface-rule branch specialization

Qualification: passes the user's revised **3% median whole-terrain gate** on the primary initialized single-worker Overworld case and on Nether. It does not meet the original 5% gate, and it is not a uniform 3% improvement across workloads. The user changed the threshold after the first gate result and before correctness work was complete. No additional production optimization was attempted after the threshold change.

Baseline: `eb3789038e3184c98a1459fe638947200217d360`, including production commit `ce77a418` from dependency [PR #796](https://github.com/ludovic111/horizon/pull/796). Production/test candidate: `69441d539aa48b8bcc82f97eaa9c7e61e5c90409`. Evidence commits add no production changes. Incremental results below compare against #796's code, not its earlier baseline. Branch `t3/optimize-surface-generation`; isolated checkout `/home/bob/.t3/worktrees/horizon/t3-7deb9745` (physical `/srv/bob-data/.t3/worktrees/horizon/t3-7deb9745`). The dependency's branch and checkout were not changed.

## Feasibility and change

Fresh `gprofng -p hi` profiles with the density kernel present use initialized 24×24 terrain regions, seed 12345, center (0,0), one worker. Timestamp filters isolate terrain from initialization and decoration. Overworld sampled terrain CPU totals 6.224 seconds: compiled rule application is 0.522 self / 0.907 inclusive seconds (8.39% / 14.57%). Nether totals 2.598 seconds: rule application is 0.321 self / 1.077 inclusive seconds (12.36% / 41.45%). Inclusive times overlap. Sampling changes runtime; these profiles select the trial, not quantify its speedup. This supported one narrow trial rather than an immediate feasibility stop.

Material conditions already cache block/column queries and compile biome predicates to constants when the supplied possible-biome set proves their result. The candidate specializes the surrounding compiled rule tree: a false constant predicate becomes an empty rule, a true one unwraps its child, and sequences omit empty rules and unwrap single remaining children. `Not` of an existing constant is also recognized. Both sides of a condition and every sequence child are still compiled first, retaining binding order, random initialization, size/depth accounting, and compilation errors even in unreachable branches. Dynamic predicates with empty children are retained, preserving their calls, cache behavior and errors. Runtime short-circuit order is unchanged.

Production changes are confined to two material-condition files (25 added / 3 removed lines). No traversal, floating-point expression, density kernel, extension algorithm, terrain storage, biome resolver, temperature state, decoration, structure or scheduling code changed.

## Declared measurement

`surface-results/workloads.json` was written before candidate editing. The primary matrix is all three dimensions, seed 12345 / center (0,0), one and four workers. The second Overworld site is seed -1 / center (32,-32), also one and four workers. Each initialized process first generates and discards an offset 9×9 region at center+(64,64), using the same seeded generator, then creates fresh measured workers. The target region is never pre-generated. Measured work is 16×16 terrain chunks (256), followed by decoration of the 14×14 interior (196). The cold one-worker case omits the initialization pass and is separate.

Each case has one discarded process pair, then five measured pairs with alternating executable order. All builds and benchmark processes are sequential. Whole-terrain timing is actual elapsed / 256 from the diagnostic JSON, not the thread-multiplied display. Combined timing is (terrain elapsed + complete phased decoration elapsed) / 256. The inherited decoration display rounds its duration; combined precision retains that limitation. Percent reduction is `100*(baseline-candidate)/baseline` applied to the two medians. This differs from the median of individual paired percentages; all individual pairs are retained.

Machine: AMD Ryzen 5 5600X (6 cores/12 logical CPUs), 32 GiB RAM, Linux 7.2.11-zen1-1-zen, Rust 1.99.0. `fast` inherits release with LTO disabled, 16 codegen units and incremental compilation. No extra Rust flags. Target `/srv/bob-data/horizon-stage3d-target`, preserving its existing `fast` symlink to `/tmp/horizon-density-eval/fast-build`. Prepared resources `/srv/bob-data/horizon/.local/horizon-client/26.3`. Both baseline and candidate were freshly built in this checkout and copied to private versioned executables. Desktop/background activity was not isolated. No unrelated artifacts or private fixtures were deleted.

## Results

Values are baseline → candidate milliseconds per input terrain chunk. Negative reductions are regressions.

- **overworld, 1 worker(s), seed 12345, center (0, 0), initialized:** terrain 10.664185 → 10.298453 ms/input chunk (3.430%); combined 12.644671 → 12.241734 (3.187%). Paired terrain range 1.575% to 4.508%; slower in 0/5 pairs. Surface bracket 3.346124 → 3.078685 (7.993%).
- **overworld, 4 worker(s), seed 12345, center (0, 0), initialized:** terrain 3.465730 → 3.379932 ms/input chunk (2.476%); combined 4.064637 → 3.980518 (2.070%). Paired terrain range -1.020% to 4.466%; slower in 1/5 pairs. Surface bracket 3.463463 → 3.197224 (7.687%).
- **the_nether, 1 worker(s), seed 12345, center (0, 0), initialized:** terrain 4.838388 → 4.637119 ms/input chunk (4.160%); combined 5.207138 → 5.011260 (3.762%). Paired terrain range 2.752% to 8.197%; slower in 0/5 pairs. Surface bracket 3.273146 → 3.073645 (6.095%).
- **the_nether, 4 worker(s), seed 12345, center (0, 0), initialized:** terrain 1.368613 → 1.314843 ms/input chunk (3.929%); combined 1.473535 → 1.420013 (3.632%). Paired terrain range -1.903% to 6.177%; slower in 1/5 pairs. Surface bracket 3.517880 → 3.338558 (5.097%).
- **the_end, 1 worker(s), seed 12345, center (0, 0), initialized:** terrain 1.035215 → 1.004687 ms/input chunk (2.949%); combined 1.106675 → 1.075390 (2.827%). Paired terrain range -1.342% to 4.824%; slower in 1/5 pairs. Surface bracket 0.334425 → 0.330838 (1.072%).
- **the_end, 4 worker(s), seed 12345, center (0, 0), initialized:** terrain 0.268664 → 0.276547 ms/input chunk (-2.934%); combined 0.297687 → 0.304711 (-2.359%). Paired terrain range -13.170% to 7.493%; slower in 2/5 pairs. Surface bracket 0.345005 → 0.354236 (-2.676%).
- **overworld, 1 worker(s), seed -1, center (32, -32), initialized:** terrain 9.774022 → 9.526515 ms/input chunk (2.532%); combined 10.799569 → 10.576202 (2.068%). Paired terrain range 0.979% to 9.116%; slower in 0/5 pairs. Surface bracket 3.697809 → 3.534839 (4.407%).
- **overworld, 4 worker(s), seed -1, center (32, -32), initialized:** terrain 2.659861 → 2.585106 ms/input chunk (2.810%); combined 2.958885 → 2.884013 (2.530%). Paired terrain range 0.481% to 5.260%; slower in 0/5 pairs. Surface bracket 3.894868 → 3.694543 (5.143%).
- **overworld, 1 worker(s), seed 12345, center (0, 0), cold:** terrain 21.423242 → 21.223466 ms/input chunk (0.933%); combined 23.400703 → 23.136161 (1.130%). Paired terrain range -4.484% to 1.671%; slower in 1/5 pairs. Surface bracket 3.363849 → 3.115849 (7.373%).

The primary single-worker Overworld result improves in all five pairs, but individual gains span 1.575–4.508%; it is not a claim that every repeat clears 3%. Nether single-worker also improves in all five pairs. Four-worker Overworld and Nether each have one slower candidate pair. End four-worker has two slower pairs and a 2.934% median regression; paired reductions range from -13.170% to 7.493%, so there is no established End four-worker gain. The second Overworld site's medians and cold result remain below 3%. No case was removed or relabeled after observing its timings.

Primary one-worker terrain process CPU medians are 10.6 → 10.2 ms/input chunk; four-worker 13.6 → 13.4. The diagnostic CPU display is quantized/rounded. Aggregate worker-stage times are not exclusive CPU shares. Peak process RSS medians are 786776 → 786864 KiB at one worker and 834404 → 834476 KiB at four, effectively unchanged. CPU/RSS for every case are in `surface-results/summary.json`; resource user/system times include initialization and other process phases. Executable `size` text totals grow 2912 bytes (5167835 → 5170747). Full hashes, sizes, commands and environment are retained.

## Correctness and exact artifact

- **102 optimized Rust tests pass:** 91 world-library tests plus 11 selected integration tests. New tests verify that constant branches retain all density bindings in order, unreachable children still fail compilation without registering a rule, short-circuit evaluation does not query removed branches, and dynamic temperature predicates on empty children retain repeated calls, biome caching and errors.
- **24/24 exact complete-field chunk comparisons pass**, covering 1,317,207,694 bytes per revision: three dimensions × two seeds/sites × one/four workers, each retaining all 81 terrain chunks and comparing both terrain and the completed 49-chunk interior decoration phase. Snapshots compare actual section palettes/storage, raw and public block states, quart biomes, binary block-entity/entity NBT, saved block/fluid ticks including delays/priorities, all six heightmaps including presence/raw words, ordered postprocessing, actual non-air counts, generation/decorated status, retrogen and structure identity/bounds metadata. The temporary count accessor is absent from production.
- **Six fresh Java client/server parity suites pass against independently authenticated pinned 26.3 artifacts:** material stage 6,733,382 matching lines on each side; rule library 678,174; conditions 5,627,426; biome temperature 836,659; extensions 233,100; surface 122,988. The material-stage suite contains 79 fixtures, 106 surface builds, 42 terrain builds, 42 generated-carving passes, 158 explicit carving passes and 7,584 top-material queries. Its cases include eroded badlands, frozen/deep frozen oceans, mixed surface-heavy biomes, all bundled terrain routers/dimensions, both seeded modes, clipped writes, repeated builds, primed/lazy heightmaps, fluids and nondefault solids. The condition/rule suites additionally exercise caches, errors, codec/binding behavior and ordered application queries. Oracle/corpus/comparison logic was unchanged.
- **The final production build is byte-identical to the measured candidate executable**, including `.text`, `.rodata` and `.data.rel.ro`. Full executable SHA-256 is `353c979ce0a3d297687015077c75b981b34b1e571e6651e7f26ec91aac943102`. `surface-results/final-codegen-check.json` records both hashes and section comparisons. Production/test commit `69441d53` is therefore the measured and validated artifact; later report commits change no production code. No standalone artifact with a different density baseline is being qualified.
- The repository PR self-check passes: public-tree validation, 236 Python tests, workspace rustfmt, clippy with warnings denied, and 162 world-crate tests. Fresh Java parity ran separately as detailed above. The size warning counts raw timing/validation evidence; production is 28 changed lines in two files, plus 172 lines of regression tests. `git diff --check` passes, and the saved production patch reverse-applies cleanly.

Validation is scoped to these workloads and corpora. The complete-field snapshots compare candidate against the baseline; their metadata coverage must not be described as complete Java world parity. Java material-stage dumps have the narrower field scope recorded in their report. Full gameplay, lighting, meshing, saving/streaming, every seed/biome and future compiler versions were not benchmarked.

## Evidence and reproduction

Public evidence: `surface-results/` contains the declared workloads, environment and binary hashes, exact production patch, raw gate/matrix timings (including warmups and commands), individual process logs, medians/pairs, sampled profiles and filters, test logs, and validation helpers/reports. Private executables, sampled experiment directories and full chunk snapshots are under `/srv/bob-data/horizon-surface-7deb9745/`. Java outputs/fixtures are ignored under `surface-results/private-parity/`; they are not committed. No game resources, private fixtures, chunk dumps or Java binaries are in the PR.

For clean reproduction, use an isolated checkout at the pinned baseline, copy `noise-aquifer-results/chunkgen_profile.rs` to `crates/horizon-world/examples/chunkgen_profile.rs`, build with the command below and copy the executable to the private `baseline` path in `surface-results/bench.py`. Apply `surface-results/candidate.patch`, rebuild identically, and copy to `candidate`. These measurements include #796 in both executables.

```sh
CARGO_TARGET_DIR=/srv/bob-data/horizon-stage3d-target cargo build --profile fast -p horizon-world --example chunkgen_profile
python3 surface-results/bench.py gate
python3 surface-results/bench.py matrix
python3 surface-results/summarize.py
```

`build_snapshots.py` copies the complete diagnostic and temporary non-air accessor from the dependency's evidence helpers, builds candidate and pinned baseline, and restores sources/removes the diagnostic on exit. `validate_chunks.py` compares all retained chunks before and after decoration in 12 cases. Java validation reuses the repository oracles and comparisons; its only adaptations are the optimized build profile and ignored local output storage. The first Java attempt aborted because the authentication helper requires generated fixture paths beneath the checkout; moving the newly generated output into that ignored directory fixed the runner without changing oracle/corpus logic.

```sh
python3 surface-results/build_snapshots.py
python3 surface-results/validate_chunks.py
CARGO_TARGET_DIR=/srv/bob-data/horizon-stage3d-target python3 surface-results/validate_java.py
CARGO_TARGET_DIR=/srv/bob-data/horizon-stage3d-target cargo test --profile fast -p horizon-world --lib --test material_rule_specialization --test material_stage --test carving_stage --test tick_data --test retrogen_biomes --test biome_region
```

Profile collection commands (each requires a new experiment directory):

```sh
HORIZON_PROFILE_WARM=1 gprofng collect app -p hi -o /path/to/new-profile.er /srv/bob-data/horizon-surface-7deb9745/baseline /srv/bob-data/horizon/.local/horizon-client/26.3 --seed 12345 --size 24 --threads 1 --dimension overworld
# Repeat with --dimension the_nether. Use that run's own PROFILE_MEASURE_START
# and PROFILE_TERRAIN_END markers in nanoseconds for gprofng's TSTAMP filter.
```

## Review dependency and next task

Review is stacked on `rdbtCVS/horizon:t3/optimize-noise-aquifers`, whose head is the pinned #796 baseline. This gives reviewers a surface-only diff while upstream does not yet contain that dependency branch. The full measured and validated head includes #796; this is not a standalone upstream artifact or a cumulative speedup claim. No change was made to #796 and nothing was merged.

For the decoration task, reprofile its interval on the accepted surface head and preserve the same equal-work denominator/border work. The already-collected Overworld sample's decoration interval has ore placement at 15.49% self / 35.24% inclusive CPU and sculk spreading at 7.84% self / 19.69% inclusive, with packed reads, height queries and region lookups also visible. These are candidate investigation sites, not optimization results. No decoration or structure implementation work was started. Cold initialization remains separate from recurring throughput.
