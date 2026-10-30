
#[test]
fn compare_every_small_history() {
    let mut cases: u64=0;let mut changes=0;let mut new_packs=0;let mut tie=0;
    for len in 0..=4u32 {
        for mut sequence in 0..8usize.pow(len) {
            let mut choices=Vec::new();
            let mut labels=Vec::new();let mut stamps=Vec::new();
            for i in 0..len {
                let v=sequence%8;sequence/=8;
                let key=match v%4 {0=>None,j=>Some(9+j as u64)};
                let time=1+(v/4);
                let tag=key.map(|k|format!("_{k:016x}_r{i}")).unwrap_or_else(||format!("old{i}"));
                choices.push(PathBuf::from(format!("s-{time:04}-{tag}-svh")));
                labels.push(key);stamps.push(time);
            }
            for mask in 0..(1usize<<len) {
                let rejected:FxHashSet<_>=choices.iter().enumerate().filter(|(i,_)|mask&(1<<i)!=0).map(|(_,p)|p.clone()).collect();
                for current in [None,Some(10u64),Some(11),Some(17)] {
                    let mut items=choices.clone();
                    items.push(PathBuf::from("s-9999-_000000000000000a_bad-working"));
                    items.insert(0,PathBuf::from("s-@@@-_000000000000000b_bad-svh"));
                    items.push(PathBuf::from("not-a-session"));
                    items.push(PathBuf::from("s-9999-_000000000000000c_r.lock"));
                    let prev=old_source_directory(items.clone().into_iter(),&rejected,current);
                    let next=find_source_directory_in_iter(items.into_iter(),&rejected,current);
                    assert_eq!(prev.0,next.0,"selection changed: {:?} {mask} {current:?}",choices);
                    let newest=stamps.iter().copied().max();
                    let latest:Vec<_>=labels.iter().zip(&stamps).filter(|(_,s)|Some(**s)==newest).map(|(k,_)|*k).collect();
                    let expect=next.0.is_some() && current.is_some() && !latest.is_empty() && latest.iter().all(|k| k.is_some() && *k!=current);
                    assert_eq!(next.1,expect,"incorrect transition in {:?} {mask} {current:?}",choices);
                    if prev.1!=next.1 {changes+=1;if next.1 {new_packs+=1;}}
                    if latest.len()>1{tie+=1;}
                    cases+=1;
                }
            }
        }
    }
    println!("cases={cases} packing_changed={changes} new_after_rejected={new_packs} with_latest_ties={tie}");
}
