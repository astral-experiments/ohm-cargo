//! Private, bounded protocol shared by Cargo and its explicitly selected compiler worker.

use std::io::{self, Read, Write};

const MAGIC: &[u8] = b"cargo-rustc-worker-v1\n";
pub const CHECK: u8 = b'C';
pub const MAX_OUTPUT: usize = 8 * 1024 * 1024;
const MAX_IDENTITY_FIELD: usize = 64 * 1024;

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Identity {
    pub compiler: String,
    pub compiler_sha256: String,
    pub driver: String,
    pub driver_sha256: String,
    pub sysroot: String,
    pub verbose_version: String,
}

pub struct Response {
    pub code: u8,
    pub reusable: bool,
    pub stdout: Vec<u8>,
    pub stderr: Vec<u8>,
}

fn invalid(message: &str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message)
}

fn write_bytes(writer: &mut impl Write, bytes: &[u8]) -> io::Result<()> {
    writer.write_all(&(bytes.len() as u64).to_le_bytes())?;
    writer.write_all(bytes)
}

fn read_bytes(reader: &mut impl Read, limit: usize) -> io::Result<Vec<u8>> {
    let mut length = [0; 8];
    reader.read_exact(&mut length)?;
    let length = usize::try_from(u64::from_le_bytes(length))
        .map_err(|_| invalid("compiler worker frame is too large"))?;
    if length > limit {
        return Err(invalid("compiler worker frame is too large"));
    }
    let mut bytes = vec![0; length];
    reader.read_exact(&mut bytes)?;
    Ok(bytes)
}

pub fn write_identity(writer: &mut impl Write, identity: &Identity) -> io::Result<()> {
    writer.write_all(MAGIC)?;
    for value in [
        &identity.compiler,
        &identity.compiler_sha256,
        &identity.driver,
        &identity.driver_sha256,
        &identity.sysroot,
        &identity.verbose_version,
    ] {
        if value.len() > MAX_IDENTITY_FIELD {
            return Err(invalid("compiler worker identity is too large"));
        }
        write_bytes(writer, value.as_bytes())?;
    }
    writer.flush()
}

pub fn read_identity(reader: &mut impl Read) -> io::Result<Identity> {
    let mut magic = vec![0; MAGIC.len()];
    reader.read_exact(&mut magic)?;
    if magic != MAGIC {
        return Err(invalid("unsupported compiler worker protocol"));
    }
    let mut string = || {
        String::from_utf8(read_bytes(reader, MAX_IDENTITY_FIELD)?)
            .map_err(|_| invalid("invalid compiler worker identity"))
    };
    Ok(Identity {
        compiler: string()?,
        compiler_sha256: string()?,
        driver: string()?,
        driver_sha256: string()?,
        sysroot: string()?,
        verbose_version: string()?,
    })
}

pub fn write_response(writer: &mut impl Write, response: &Response) -> io::Result<()> {
    if response.stdout.len().saturating_add(response.stderr.len()) > MAX_OUTPUT {
        return Err(invalid("compiler worker output exceeds its limit"));
    }
    writer.write_all(&[response.code, u8::from(response.reusable)])?;
    write_bytes(writer, &response.stdout)?;
    write_bytes(writer, &response.stderr)?;
    writer.flush()
}

pub fn read_response(reader: &mut impl Read) -> io::Result<Response> {
    let mut header = [0; 2];
    reader.read_exact(&mut header)?;
    if header[0] > 1 || header[1] > 1 {
        return Err(invalid("invalid compiler worker result"));
    }
    let stdout = read_bytes(reader, MAX_OUTPUT)?;
    let stderr = read_bytes(reader, MAX_OUTPUT - stdout.len())?;
    Ok(Response {
        code: header[0],
        reusable: header[1] != 0,
        stdout,
        stderr,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn responses_preserve_channels_and_request_boundaries() {
        let mut bytes = Vec::new();
        for text in [b"first\n\0".as_slice(), b"second".as_slice()] {
            write_response(
                &mut bytes,
                &Response {
                    code: 0,
                    reusable: true,
                    stdout: text.to_vec(),
                    stderr: b"diagnostic\n".to_vec(),
                },
            )
            .unwrap();
        }
        let mut reader = bytes.as_slice();
        assert_eq!(read_response(&mut reader).unwrap().stdout, b"first\n\0");
        let second = read_response(&mut reader).unwrap();
        assert_eq!(second.stdout, b"second");
        assert_eq!(second.stderr, b"diagnostic\n");
        assert!(reader.is_empty());
    }

    #[test]
    fn output_and_identity_frames_are_bounded() {
        let mut oversized = vec![0, 1];
        oversized.extend_from_slice(&(MAX_OUTPUT as u64 + 1).to_le_bytes());
        assert!(read_response(&mut oversized.as_slice()).is_err());
        assert!(read_identity(&mut b"invalid protocol header".as_slice()).is_err());
    }
}
