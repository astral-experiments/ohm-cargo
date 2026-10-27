use std::collections::BTreeMap;
use std::fs::File;
use std::io::{self, Read};
use std::path::{Path, PathBuf};
use std::time::Instant;

fn checksum(path: &Path, buffer: &mut [u8]) -> io::Result<blake3::Hash> {
    let mut source = File::open(path)?;
    let mut hasher = blake3::Hasher::new();
    loop {
        let read = source.read(buffer)?;
        if read == 0 {
            break;
        }
        hasher.update(&buffer[..read]);
    }
    Ok(hasher.finalize())
}

fn verify(paths: &[PathBuf], worker: bool) -> io::Result<BTreeMap<PathBuf, blake3::Hash>> {
    let mut results = BTreeMap::new();
    let mut buf = vec![0; 64 * 1024];
    // These are the cache misses of the first, rmeta-only reader. The later reader
    // sees those digests in Cargo's per-invocation cache and checks the other files.
    for meta in [true, false] {
        let inputs: Vec<_> = paths.iter().filter(|p| (p.extension().unwrap() == "rmeta") == meta).collect();
        let largest = if worker && meta {
            inputs.iter().copied().max_by_key(|p| p.metadata().unwrap().len())
        } else {
            None
        };
        std::thread::scope(|scope| -> io::Result<()> {
            let helper = largest.map(|p| scope.spawn(move || checksum(p, &mut vec![0; 64 * 1024])));
            for path in inputs.iter().copied().filter(|p| Some(*p) != largest) {
                results.insert(path.clone(), checksum(path, &mut buf)?);
            }
            if let (Some(job), Some(path)) = (helper, largest) {
                results.insert(path.clone(), job.join().unwrap()?);
            }
            Ok(())
        })?;
    }
    Ok(results)
}

fn main() -> io::Result<()> {
    let mut args = std::env::args_os().skip(1);
    let sdk = PathBuf::from(args.next().expect("SDK library directory"));
    let names = std::fs::read_to_string(args.next().expect("SDK file list"))?;
    let files: Vec<_> = names.lines().map(|n| sdk.join(n)).collect();
    assert_eq!(files.len(), 39);
    let expected = verify(&files, false)?;
    println!("phase,implementation,nanoseconds");
    // Both variants use identical BLAKE3 and the same two receipt miss groups.
    for (phase, first) in [false,true,true,false,true,false,false,true].into_iter().enumerate() {
        for worker in [first, !first] {
            let start = Instant::now();
            let current = verify(&files, worker)?;
            let elapsed = start.elapsed().as_nanos();
            assert_eq!(current, expected);
            println!("{},{},{}", phase + 1, if worker { "helper" } else { "serial" }, elapsed);
        }
    }
    for (p, h) in expected {
        eprintln!("{}  {}", h, p.file_name().unwrap().to_str().unwrap());
    }
    Ok(())
}
