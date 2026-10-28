use rustc_hash::FxHashMap;
use std::collections::BTreeSet;
use std::io::{self, Write as _};
use std::path::{Path,PathBuf};
fn main() {
    let mut args=std::env::args().skip(1); let mode=args.next().unwrap();
    let input=std::fs::read_to_string(args.next().unwrap()).unwrap();
    let groups: Vec<Vec<PathBuf>>=input.trim_end().split("\n\n").map(|chunk|chunk.lines().map(PathBuf::from).collect()).collect();
    let all=||groups.iter().flat_map(|group|group.iter().cloned()).collect::<Vec<_>>();
    let mut rendered=Vec::new();
    for _ in 0..4 {
        rendered.clear();
        let mut write=|path:&Path|writeln!(&mut rendered,"{}",path.to_str().unwrap()).unwrap();
        match mode.as_str() {
            "map-tree" => {
                let mut set=BTreeSet::new();
                for group in &groups {
                    let mut map=FxHashMap::default();
                    map.extend(group.iter().enumerate().filter_map(|(index,p)| (std::hint::black_box(index)!=usize::MAX).then(||(p.clone(),Some((1u64,[0u8;32]))))));
                    set.extend(map.into_keys());
                }
                for p in set { write(&p); }
            }
            "tree" => { let mut set=BTreeSet::new();for group in &groups {set.extend(group.iter().cloned());}for p in set {write(&p);} }
            "sort" => {let mut v=all();v.sort();v.dedup();for p in v {write(&p);}}
            "components" => {
                let v=all();let mut refs:Vec<_>=v.iter().map(PathBuf::as_path).collect();
                refs.sort_by_cached_key(|p|p.components().collect::<Vec<_>>());
                refs.dedup();for p in refs {write(p);}
            }
            _ => unreachable!(),
        }
        std::hint::black_box(&rendered);
    }
    io::stdout().lock().write_all(&rendered).unwrap();
}
