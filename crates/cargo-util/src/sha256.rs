use super::paths;
use anyhow::{Context, Result};
use sha2::{Digest, Sha256 as Sha2_sha256};
use std::fs::File;
use std::io::{self, BufRead, BufReader};
use std::path::Path;

pub struct Sha256(Sha2_sha256);

impl Sha256 {
    pub fn new() -> Sha256 {
        let hasher = Sha2_sha256::new();
        Sha256(hasher)
    }

    pub fn update(&mut self, bytes: &[u8]) -> &mut Sha256 {
        let _ = self.0.update(bytes);
        self
    }

    pub fn update_file(&mut self, file: &File) -> io::Result<&mut Sha256> {
        // Let File fill the buffer without first zeroing 64 KiB for each
        // small input, such as a cached compiler message.
        let mut reader = BufReader::with_capacity(64 * 1024, file);
        loop {
            let bytes = reader.fill_buf()?;
            if bytes.is_empty() {
                return Ok(self);
            }
            self.update(bytes);
            let n = bytes.len();
            reader.consume(n);
        }
    }

    pub fn update_path<P: AsRef<Path>>(&mut self, path: P) -> Result<&mut Sha256> {
        let path = path.as_ref();
        let file = paths::open(path)?;
        self.update_file(&file)
            .with_context(|| format!("failed to read `{}`", path.display()))?;
        Ok(self)
    }

    pub fn finish(&mut self) -> [u8; 32] {
        self.0.finalize_reset().into()
    }

    pub fn finish_hex(&mut self) -> String {
        hex::encode(self.finish())
    }
}

impl Default for Sha256 {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::Sha256;
    use std::io::{Seek, SeekFrom, Write};

    #[test]
    fn hashes_from_the_current_offset_through_eof() {
        let bytes: Vec<_> = (0..2 * 64 * 1024 + 7).map(|i| i as u8).collect();
        let mut file = tempfile::tempfile().unwrap();
        file.write_all(&bytes).unwrap();
        for len in [0, 1, 85, 64 * 1024, 64 * 1024 + 1, bytes.len()] {
            let offset = bytes.len() - len;
            file.seek(SeekFrom::Start(offset as u64)).unwrap();
            let expected = Sha256::new().update(&bytes[offset..]).finish();
            assert_eq!(Sha256::new().update_file(&file).unwrap().finish(), expected);
            assert_eq!(file.stream_position().unwrap(), bytes.len() as u64);
        }
    }
}
