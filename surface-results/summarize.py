"""Summarize sequential equal-work pairs, excluding only declared warmups."""
import json
import pathlib
import statistics

root = pathlib.Path(__file__).resolve().parent
rows = []
for name in ['gate', 'matrix']:
    path = root / (name + '-raw.json')
    if path.exists():
        rows.extend(json.loads(path.read_text()))
cases = dict.fromkeys((r['dimension'], r['threads'], r['seed'], tuple(r['center']), r['warm']) for r in rows)
summary = []
for dim, threads, seed, center, warm in cases:
    selected = [r for r in rows if (r['dimension'], r['threads'], r['seed'], tuple(r['center']), r['warm']) == (dim, threads, seed, center, warm) and r['repeat'] >= 0]
    result = dict(dimension=dim, threads=threads, seed=seed, center=center, warm=warm)
    result['measured_count'] = {v: sum(r['version'] == v for r in selected) for v in ['baseline', 'candidate']}
    for metric in ['wall_ms_chunk', 'combined_ms_chunk', 'noise', 'surface', 'terrain_cpu_ms_chunk', 'peak_rss_kib', 'process_user_s', 'process_system_s']:
        values = {v: statistics.median(r[metric] for r in selected if r['version'] == v) for v in ['baseline', 'candidate']}
        result[metric] = dict(values, reduction_percent=100 * (values['baseline'] - values['candidate']) / values['baseline'])
    pairs = []
    for repeat in range(5):
        pair = {r['version']: r['wall_ms_chunk'] for r in selected if r['repeat'] == repeat}
        if len(pair) == 2:
            pairs.append(dict(repeat=repeat, **pair, reduction_percent=100 * (pair['baseline'] - pair['candidate']) / pair['baseline']))
    result['pairs'] = pairs
    summary.append(result)
(root / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
for r in summary:
    t, c = r['wall_ms_chunk'], r['combined_ms_chunk']
    print(f"{r['dimension']} t{r['threads']} seed{r['seed']} warm{int(r['warm'])}: terrain {t['baseline']:.6f} -> {t['candidate']:.6f} ({t['reduction_percent']:.3f}%); combined {c['baseline']:.6f} -> {c['candidate']:.6f} ({c['reduction_percent']:.3f}%)")
