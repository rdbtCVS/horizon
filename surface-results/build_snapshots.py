"""Build both complete-field diagnostics, restoring production sources on exit."""
import os
import pathlib
import shutil
import subprocess

root = pathlib.Path(__file__).resolve().parents[1]
results = pathlib.Path(__file__).parent
work = pathlib.Path('/srv/bob-data/horizon-surface-7deb9745')
target = pathlib.Path('/srv/bob-data/horizon-stage3d-target')
env = dict(os.environ, CARGO_TARGET_DIR=str(target))
paths = [root / 'crates/horizon-world/src/worldgen' / name for name in ['material_condition.rs', 'material_condition/rule.rs', 'terrain.rs']]
original = {p: p.read_bytes() for p in paths}
example = root / 'crates/horizon-world/examples/chunkgen_snapshot.rs'
assert not example.exists()
try:
    shutil.copyfile(root / 'noise-aquifer-results/chunkgen_snapshot.rs', example)
    subprocess.run(['git', 'apply', 'noise-aquifer-results/snapshot-accessor.patch'], cwd=root, check=True)
    for version in ['candidate', 'baseline']:
        if version == 'baseline':
            for p in paths[:2]:
                p.write_bytes(subprocess.check_output(['git', 'show', 'eb3789038e3184c98a1459fe638947200217d360:' + str(p.relative_to(root))], cwd=root))
        with (results / ('snapshot-' + version + '-build.log')).open('w') as log:
            subprocess.run(['cargo', 'build', '--profile', 'fast', '-p', 'horizon-world', '--example', 'chunkgen_snapshot'], cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        shutil.copy2(target / 'fast/examples/chunkgen_snapshot', work / ('snapshot-' + version))
finally:
    for p, content in original.items():
        p.write_bytes(content)
    example.unlink(missing_ok=True)
