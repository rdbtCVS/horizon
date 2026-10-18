"""Fresh repository Java oracles; only build profile and private storage adapted."""
import hashlib
import json
import pathlib
import sys

root = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'tools'))
import lab

private = pathlib.Path(__file__).resolve().parent / 'private-parity'
private.mkdir(exist_ok=True)
if not (private / 'minecraft').exists():
    (private / 'minecraft').symlink_to('/srv/bob-data/horizon/.local/minecraft', target_is_directory=True)
lab.LOCAL = private
for kind in sys.argv[1:] or ['material_stage', 'material_rule_library', 'material_condition', 'biome_temperature', 'material_extension', 'material_surface']:
    script = root / 'tools' / ('test_' + kind + '_parity.py')
    source = script.read_text()
    source = source.replace("'cargo','build','--release'", "'cargo','build','--profile','fast'")
    source = source.replace('"cargo","build","--release"', '"cargo","build","--profile","fast"')
    source = source.replace("/'release/examples'/", "/'fast/examples'/").replace('/"release/examples"/', '/"fast/examples"/')
    namespace = {'__file__': str(script), '__name__': 'surface_java_validation'}
    sys.argv = [str(script)]
    exec(compile(source, str(script), 'exec'), namespace)
    namespace['main']()
    report = json.loads((private / ('rust-' + kind.replace('_', '-') + '-parity') / 'report.json').read_text())
    report['harness_adjustments'] = dict(profile='fast', private_storage=str(private), original_harness_sha256=hashlib.sha256(script.read_bytes()).hexdigest())
    (pathlib.Path(__file__).parent / (kind + '-parity.json')).write_text(json.dumps(report, indent=2) + '\n')
