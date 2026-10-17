//! Full production fact loading, including file reads, interning and temporary destruction.
//! cargo run --profile fast -p horizon-client --example block_facts_bench -- ROOT [SAMPLES]
//! Use SAMPLES=1 with an OS peak-RSS wrapper; `digest` checks all facts
//! and the shape sharing partition (including sharing between outlines and edges).
use horizon_block_facts::BlockFacts;
use horizon_world::{DATA_VERSION, nbt::Tag, registry::BlockRegistry};
use serde_json::Value;
use std::{
    collections::{HashMap, hash_map::DefaultHasher},
    fs,
    hash::{Hash, Hasher},
    hint::black_box,
    path::Path,
    time::Instant,
};
type Result<T> = horizon_block_facts::Result<T>;

fn tag(value: &Value) -> Result<Tag> {
    Ok(match value {
        Value::String(s) => Tag::String(s.as_str().into()),
        Value::Number(n) => Tag::Int(i32::try_from(n.as_i64().ok_or("registry number")?)?),
        Value::Array(a) => Tag::List(a.iter().map(tag).collect::<Result<_>>()?),
        Value::Object(o) => Tag::Compound(
            o.iter()
                .map(|(k, v)| Ok((k.as_str().into(), tag(v)?)))
                .collect::<Result<_>>()?,
        ),
        _ => return Err("registry value".into()),
    })
}
fn registry(root: &Path, mode: &str) -> Result<BlockRegistry> {
    let mut facts: Value = serde_json::from_slice(&fs::read(root.join("facts.json"))?)?;
    if mode == "registry-property" {
        // A caller may construct a registry with different properties while
        // the cached resource files still have exactly the same hashes.
        let states = facts["states"].as_array_mut().ok_or("registry states")?;
        let grass = states
            .iter_mut()
            .find(|s| s[0] == "minecraft:grass_block" && s[4]["properties"]["snowy"] == "true")
            .ok_or("snowy grass state")?;
        grass[4]["properties"]["snowy"] = Value::String("modified".into());
    } else if mode == "registry-default" {
        let states = facts["states"].as_array().ok_or("registry states")?;
        let alternative = states
            .iter()
            .enumerate()
            .find(|(i, s)| {
                s[0] == "minecraft:grass_block"
                    && *i
                        != facts["defaults"]["minecraft:grass_block"]
                            .as_u64()
                            .unwrap_or(u64::MAX) as usize
            })
            .ok_or("alternative grass default")?
            .0;
        facts["defaults"]["minecraft:grass_block"] = Value::from(alternative as u64);
    }
    Ok(BlockRegistry::from_nbt(&Tag::compound([
        ("DataVersion", Tag::Int(DATA_VERSION)),
        (
            "states",
            Tag::List(
                facts["states"]
                    .as_array()
                    .ok_or("registry states")?
                    .iter()
                    .map(|s| tag(&s[4]))
                    .collect::<Result<_>>()?,
            ),
        ),
        ("defaults", tag(&facts["defaults"])?),
    ]))?)
}
pub fn main() -> Result<()> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    let root = Path::new(
        args.first()
            .ok_or("usage: block_facts_bench ROOT [SAMPLES|digest]")?,
    );
    let mode = args.get(1).map(String::as_str).unwrap_or("");
    let setup = Instant::now();
    let registry = registry(root, mode)?;
    println!(
        "registry_setup_ms={:.3}",
        setup.elapsed().as_secs_f64() * 1000.0
    );
    if args.get(1).is_some_and(|s| s == "prepare") {
        let start = Instant::now();
        BlockFacts::prepare_cache(root)?;
        println!("prepare_ms={:.3}", start.elapsed().as_secs_f64() * 1000.0);
        return Ok(());
    }
    if matches!(mode, "digest" | "registry-property" | "registry-default") {
        let facts = BlockFacts::load(root, &registry)?;
        let mut hash = DefaultHasher::new();
        let mut shapes = HashMap::new();
        facts.air.hash(&mut hash);
        for state in &facts.states {
            format!("{state:?}").hash(&mut hash);
            for shape in [&state.outline, &state.outline_edges] {
                let next = shapes.len();
                shapes
                    .entry((shape.as_ptr(), shape.len()))
                    .or_insert(next)
                    .hash(&mut hash);
            }
        }
        println!(
            "states={} shared_shapes={} digest={:016x}",
            facts.states.len(),
            shapes.len(),
            hash.finish()
        );
        return Ok(());
    }
    let samples: usize = args.get(1).map(|s| s.parse()).transpose()?.unwrap_or(9);
    assert!(samples > 0);
    // First load is reported separately; OS file caches are not forcibly evicted.
    let load = || -> Result<f64> {
        let start = Instant::now();
        let facts = black_box(BlockFacts::load(black_box(root), black_box(&registry))?);
        let ms = start.elapsed().as_secs_f64() * 1000.0;
        drop(facts);
        Ok(ms)
    };
    println!("first_load_ms={:.3}", load()?);
    if samples > 1 {
        load()?;
        load()?;
        let mut times = (0..samples).map(|_| load()).collect::<Result<Vec<_>>>()?;
        println!("samples_ms={times:.3?}");
        times.sort_by(f64::total_cmp);
        println!("median_ms={:.3}", times[times.len() / 2]);
    }
    Ok(())
}
