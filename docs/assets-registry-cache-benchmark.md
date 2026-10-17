# Registry cache: correctness, compatibility and measured startup cost

## Decision

Keep the versioned, validated typed registry cache. The early **debug-profile** registry
measurements suggested a regression (435.4 ms warm vs 403.0 ms direct). That comparison was
not representative of the optimised binary. Two repeated **fast-profile** microbenchmark
runs with the same registry lookup and prepared facts measured 50–51 ms warm cache decoding
versus 133–135 ms direct JSON-to-NBT conversion. The controlled asset/item loader comparison
also showed a consistent warm-cache improvement over both baselines. Cold cache creation
remains slightly slower than direct loading.

The faster state-to-ID `HashMap` is a separate improvement. The full-loader comparison
below explicitly includes a direct-conversion build with the improved lookup, so the
cache-specific contribution can be distinguished from the lookup change.

## Three-way end-to-end comparison (12 samples each)

All variants use the same pinned Minecraft 26.3 prepared resource export, `fast` Cargo
profile, machine and private writable resource root. The binaries were built before
benchmarking, and no Cargo/rustc processes were observed at benchmark boundaries.
Each sample launches a new process. A priming run precedes the measured warm groups.
The benchmark's `total_ms` covers `Assets::load` and item renderer preparation, **not**
launcher, GPU, GUI, network startup, or the first displayed frame.

The complete per-run values, including the individual asset and item timings,
are preserved in [`docs/benchmarks/pr597-registry-startup-20261017.json`](benchmarks/pr597-registry-startup-20261017.json).

| Variant | Assets median (ms) | Total median (ms) | Total MAD (ms) | Total range (ms) |
| --- | ---: | ---: | ---: | ---: |
| Original NBT + ordered `BTreeMap` state lookup (`f535d1b4`) | 463.542 | 499.497 | 11.423 | 486.164–524.847 |
| Direct JSON-to-NBT + improved `HashMap` lookup (experimental no-cache candidate) | 485.102 | 521.024 | 14.877 | 500.679–544.611 |
| Validated typed cache, **cold**, `HashMap` lookup (`568a38b5`) | 478.352 | 513.121 | 6.943 | 504.239–531.936 |
| Validated typed cache, **warm**, `HashMap` lookup (`568a38b5`) | **389.453** | **430.217** | 18.857 | 404.564–484.007 |

The cached warm-loader median is 13.9% lower than the original and 17.4% lower
than the improved-lookup no-cache candidate in this batch. Cold cache creation is
2.7% slower than the original. The direct HashMap-only variant was 4.3% slower
than the original in this batch: **do not attribute the warm-cache gain to the
lookup change alone**. An earlier 10-sample batch found the original at 517.266 ms
and the cached warm variant at 428.983 ms; it agrees on warm-cache benefit but
shows normal variability across runs.

## Registry-only microbenchmark: optimised `fast` profile

The `benchmark_registry_conversion_only` ignored test pre-parses `facts.json`,
then alternates direct conversion with cache reuse, deleting the cache for each
cold measurement. All paths construct and validate the same registry, including
its `HashMap` state lookup. The return value is consumed with `black_box`.
Twenty measured iterations were used per path in each of **two** runs. Values:

| Run | Direct conversion median / range | Cold creation median / range | Warm decoding median / range |
| --- | --- | --- | --- |
| First | 135.260 / 128.812–164.533 ms | 150.230 / 143.056–185.947 ms | **51.210 / 47.368–53.457 ms** |
| Repeat | 132.631 / 128.716–158.619 ms | 147.808 / 142.825–170.283 ms | **50.262 / 47.426–71.051 ms** |

Warm typed-cache loading saves approximately 62% of the direct registry-conversion
stage in this configuration. Initial cache creation costs about 15 ms more than
conversion alone, including encoding, hashing and durable atomic publication.
The initial debug-profile result (direct 402.985, warm 435.357 and cold 703.097 ms)
remains recorded as a profiling lesson, but **must not be used to characterise
release-profile performance**.

## Compatibility and cache lifecycle

`Assets::load` always parses `facts.json` and checks the pinned resource manifest.
On an absent, stale, corrupt, oversized or unreadable cache, it uses the original
JSON-to-NBT conversion and the existing `BlockRegistry::from_nbt` validation;
this retains original error behaviour for invalid registry data. A cached registry
preserves ordered states and their exact IDs, property values and block default IDs.
The internal HashMap affects lookup performance only; it does not establish IDs.

Cache data is format-versioned and bound to SHA-256 of the *entire* source facts and
its own payload checksum. The decoder checks bounds, trailing bytes, UTF-8,
property duplicates, registry consistency and default-state coverage. Independent
processes and threads use unique `create_new` temporary files and atomic rename
publication; best-effort file and parent-directory syncing reduces exposure to
interrupted writes. Cache persistence is optional for read-only resource roots.
Content-mod overlays are destroyed and recreated at launch, so their registry
cache lives in the sibling cache directory and is invalidated by source changes.
Resource-pack model reloads use the established `Assets::reload` path and retain
the existing block registry.

Regression coverage checks all state IDs, properties and defaults against the
original conversion; malformed, absent and read-only resources; stale/corrupt
cache recovery; malicious but internally inconsistent payloads even with updated
checksums; concurrent writers; and content-mod overlay rebuild. The full prepared
resource integration test exercises real modded state tables.

## Reproduce

Build each checkout separately at the cited commit, with:

```sh
cargo build --offline --profile fast -p horizon-client --example model_library_bench
```

Run from the PR checkout with a **disposable** `RESOURCE_ROOT`, preserving the
same resource files for all variants:

```sh
python3 tools/profile_client_startup.py --metric startup --warm-cache \
  --binary /PATH/ORIGINAL/target/fast/examples/model_library_bench \
  --resources RESOURCE_ROOT --repeats 12
python3 tools/profile_client_startup.py --metric startup --warm-cache \
  --binary /PATH/NO_CACHE/target/fast/examples/model_library_bench \
  --resources RESOURCE_ROOT --repeats 12
python3 tools/profile_client_startup.py --metric startup --cold-cache \
  --binary /PATH/CACHED/target/fast/examples/model_library_bench \
  --resources RESOURCE_ROOT --repeats 12
python3 tools/profile_client_startup.py --metric startup --warm-cache \
  --binary /PATH/CACHED/target/fast/examples/model_library_bench \
  --resources RESOURCE_ROOT --repeats 12
```

`--cold-cache` deletes the target root's derived cache before each run. For the
registry-only benchmark, build the test binary in the matching optimised profile:

```sh
cargo test --offline --profile fast -p horizon-client --lib --no-run
HORIZON_REGISTRY_BENCH_FACTS=/ABSOLUTE/PATH/facts.json \
  /PATH/TO/target/fast/deps/horizon_client-TEST_HASH \
  benchmark_registry_conversion_only --ignored --nocapture
```

The `HORIZON_REGISTRY_BENCH_FACTS` path **must be absolute**, because Cargo tests
run from their package directory. The profiler reports all raw samples, median,
median absolute deviation and range. End-to-end UI startup, first rendered frame,
disk power-loss simulation, cross-process overlay rebuilding, and other hardware
configurations have not been measured.
