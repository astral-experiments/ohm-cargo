//! Reuse a successful Git index checksum verification for the exact same index bytes.

use std::fs::OpenOptions;
use std::io::{Read, Write};
use std::os::unix::fs::{MetadataExt as _, OpenOptionsExt as _};
use std::sync::LazyLock;

use crate::util::GlobalContext;
use crate::workspace::parser::registry_cache::private_directory;

const MIN: u64 = 256 * 1024;
const MAX: u64 = 8 * 1024 * 1024;

// A new dependency graph may have different Git collision checks or decoding behavior.
static DOMAIN: LazyLock<[u8; 32]> = LazyLock::new(|| {
    blake3::derive_key(
        "Ohm Git SHA1DC index verification v1",
        include_bytes!("../../../Cargo.lock"),
    )
});

pub(super) fn open(repo: &gix::Repository, gctx: &GlobalContext) -> Option<gix::index::File> {
    let kind = repo.object_hash();
    if kind != gix::hash::Kind::Sha1 || repo.git_dir_trust() != gix::sec::Trust::Full {
        return None;
    }
    let config = repo.config_snapshot();
    // Git permits implicit values, such as a bare `skipHash` key.
    if ["index.skipHash", "gitoxide.objects.allocLimit"]
        .iter()
        .any(|key| config.try_boolean(*key).is_some())
    {
        return None;
    }
    let thread_limit = config
        .string("index.threads")
        .map(|value| gix::config::tree::Index::THREADS.try_into_index_threads(value))
        .transpose()
        .ok()?;
    let path = repo.index_path();
    let file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(&path)
        .ok()?;
    let meta = file.metadata().ok()?;
    if !meta.is_file() || !(MIN..=MAX).contains(&meta.len()) {
        return None;
    }
    let dir = private_directory(gctx.home().as_path_unlocked(), ".ohm-git-index-sha1dc-v1")?;
    let mut data = Vec::with_capacity(meta.len() as usize);
    file.take(meta.len() + 1).read_to_end(&mut data).ok()?;
    if data.len() as u64 != meta.len() {
        return None;
    }
    let (body, trailer) = data.split_at(data.len() - kind.len_in_bytes());
    let expected = gix::hash::ObjectId::from_bytes_or_panic(trailer);
    if expected.is_null() {
        return None;
    }
    let key = blake3::keyed_hash(&DOMAIN, &data);
    let slot = u16::from_be_bytes([key.as_bytes()[0], key.as_bytes()[1]]) >> 4;
    let record = dir.join(format!("{slot:03x}"));
    let hit = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(&record)
        .ok()
        .and_then(|mut file| {
            let meta = file.metadata().ok()?;
            // SAFETY: geteuid has no arguments or memory-safety requirements.
            if !meta.is_file()
                || meta.len() != 32
                || meta.uid() != unsafe { libc::geteuid() }
                || meta.mode() & 0o077 != 0
            {
                return None;
            }
            let mut stored = [0; 32];
            file.read_exact(&mut stored).ok()?;
            Some(stored)
        })
        .is_some_and(|stored| &stored == key.as_bytes());
    if !hit {
        gix::hash::bytes(
            &mut &*body,
            body.len() as u64,
            kind,
            &mut gix::progress::Discard,
            &Default::default(),
        )
        .ok()?
        .verify(&expected)
        .ok()?;
    }
    let (state, checksum) = gix::index::State::from_bytes(
        &data,
        filetime::FileTime::from_last_modification_time(&meta),
        kind,
        gix::index::decode::Options {
            thread_limit,
            expected_checksum: Some(expected),
            ..Default::default()
        },
    )
    .ok()?;
    if state.link().is_some() || checksum != Some(expected) {
        return None;
    }
    if !hit {
        if let Ok(mut tmp) = tempfile::NamedTempFile::new_in(dir) {
            if tmp.write_all(key.as_bytes()).is_ok() {
                let _ = tmp.persist(record);
            }
        }
    }
    tracing::debug!(target: "cargo::sources::path::verified_index", hit, "verified Git index");
    Some(gix::index::File::from_state(state, path))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::os::unix::fs::PermissionsExt as _;

    #[test]
    fn receipts_verify_exact_bytes_and_defer_split_indices_to_git() {
        let root = tempfile::Builder::new()
            .permissions(fs::Permissions::from_mode(0o700))
            .tempdir()
            .unwrap();
        let path = root.path().join("work");
        gix::init(&path).unwrap();
        let repo = gix::open_opts(&path, gix::open::Options::isolated()).unwrap();
        let context = || {
            GlobalContext::new(
                cargo_util_terminal::Shell::new(),
                path.clone(),
                root.path().to_owned(),
            )
        };
        // An optional extension makes a valid, empty index large enough to qualify.
        let mut contents = b"DIRC\0\0\0\x02\0\0\0\0TEST".to_vec();
        contents.extend_from_slice(&(MIN as u32).to_be_bytes());
        contents.resize(contents.len() + MIN as usize, 0);
        let write_index = |body: &[u8]| {
            let hash = gix::hash::bytes(
                &mut &body[..],
                body.len() as u64,
                repo.object_hash(),
                &mut gix::progress::Discard,
                &Default::default(),
            )
            .unwrap();
            let bytes = [body, hash.as_slice()].concat();
            fs::write(repo.index_path(), &bytes).unwrap();
            bytes
        };
        let mut bytes = write_index(&contents);
        let directory = root.path().join(".ohm-git-index-sha1dc-v1");
        let mut disabled = context();
        disabled.nightly_features_allowed = true;
        disabled
            .configure(
                0,
                false,
                None,
                false,
                false,
                true,
                &None,
                &["ohm-defaults=no".into()],
                &[],
            )
            .unwrap();
        let package = super::super::PackageRepository::new(repo.clone());
        assert!(package.index(&disabled).is_ok());
        assert!(!directory.exists());

        let gctx = context();
        assert!(open(&repo, &gctx).is_some());
        let receipt = fs::read_dir(&directory)
            .unwrap()
            .next()
            .unwrap()
            .unwrap()
            .path();
        let digest = fs::read(&receipt).unwrap();
        let earlier = filetime::FileTime::from_unix_time(1, 0);
        filetime::set_file_mtime(&receipt, earlier).unwrap();
        assert!(open(&repo, &gctx).is_some());
        assert_eq!(
            filetime::FileTime::from_last_modification_time(&fs::metadata(&receipt).unwrap()),
            earlier
        );

        bytes[32] ^= 1;
        fs::write(repo.index_path(), &bytes).unwrap();
        filetime::set_file_mtime(repo.index_path(), earlier).unwrap();
        assert!(open(&repo, &gctx).is_none());
        assert!(repo.open_index().is_err());
        assert_eq!(fs::read(&receipt).unwrap(), digest);

        write_index(&contents);
        fs::write(&receipt, [0u8; 32]).unwrap();
        assert!(open(&repo, &gctx).is_some());
        assert_eq!(fs::read(&receipt).unwrap(), digest);
        let configured = gix::open_opts(
            path,
            gix::open::Options::isolated().cli_overrides(["index.skipHash"]),
        )
        .unwrap();
        assert!(open(&configured, &gctx).is_none());

        contents.extend_from_slice(b"link\0\0\0\x14");
        contents.extend_from_slice(&[1u8; 20]);
        write_index(&contents);
        assert!(open(&repo, &gctx).is_none());
        assert!(repo.open_index().is_err());
        assert_eq!(fs::read_dir(directory).unwrap().count(), 1);
    }
}
