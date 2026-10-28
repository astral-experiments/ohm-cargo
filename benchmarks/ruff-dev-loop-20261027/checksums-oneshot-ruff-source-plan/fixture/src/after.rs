use super::Sha256;
use std::io::{self,Read};
#[derive(Copy, Clone, Debug, Eq, PartialEq)]
pub enum ChecksumAlgo {
    Sha256,
    Blake3,
}

impl ChecksumAlgo {
    fn hash_len(&self) -> usize {
        match self {
            ChecksumAlgo::Sha256 | ChecksumAlgo::Blake3 => 32,
        }
    }
}

#[derive(Copy, Clone, Debug, Eq, PartialEq)]
pub struct Checksum {
    algo: ChecksumAlgo,
    /// If the algorithm uses fewer than 32 bytes, then the remaining bytes will be zero.
    value: [u8; 32],
}

impl Checksum {
    pub fn new(algo: ChecksumAlgo, value: [u8; 32]) -> Self {
        Self { algo, value }
    }

    pub fn compute(
        algo: ChecksumAlgo,
        contents: impl Read,
        buf: &mut [u8],
    ) -> Result<Self, io::Error> {
        assert!(!buf.is_empty());
        let mut ret = Self {
            algo,
            value: [0; 32],
        };
        let len = algo.hash_len();
        let value = &mut ret.value[..len];

        fn digest<T>(
            mut hasher: T,
            mut update: impl FnMut(&mut T, &[u8]),
            finish: impl FnOnce(T, &mut [u8]),
            mut contents: impl Read,
            buf: &mut [u8],
            value: &mut [u8],
        ) -> Result<(), io::Error> {
            loop {
                let bytes_read = contents.read(buf)?;
                if bytes_read == 0 {
                    break;
                }
                update(&mut hasher, &buf[0..bytes_read]);
            }
            finish(hasher, value);
            Ok(())
        }

        match algo {
            ChecksumAlgo::Sha256 => {
                digest(
                    Sha256::new(),
                    |h, b| {
                        h.update(b);
                    },
                    |mut h, out| out.copy_from_slice(&h.finish()),
                    contents,
                    buf,
                    value,
                )?;
            }
            ChecksumAlgo::Blake3 => {
                let mut contents = contents;
                let mut hasher = blake3::Hasher::new();
                let first = contents.read(buf)?;
                if first == 0 {
                    return Ok(Self::new(algo, *hasher.finalize().as_bytes()));
                }
                if first < buf.len() {
                    // A short read is not necessarily EOF. Preserve the original read size
                    // for record-oriented inputs that can discard the rest of a packet.
                    let prefix = buf[..first].to_vec();
                    let next = contents.read(buf)?;
                    if next == 0 {
                        return Ok(Self::new(algo, *blake3::hash(&prefix).as_bytes()));
                    }
                    hasher.update(&prefix);
                    hasher.update(&buf[..next]);
                } else {
                    hasher.update(buf);
                }
                digest(
                    hasher,
                    |h, b| {
                        h.update(b);
                    },
                    |h, out| out.copy_from_slice(h.finalize().as_bytes()),
                    contents,
                    buf,
                    value,
                )?;
            }
        }
        Ok(ret)
    }

    pub fn bytes(self) -> [u8;32] { self.value }
}
