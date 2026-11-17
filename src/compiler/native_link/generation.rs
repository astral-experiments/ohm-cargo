use std::fs::{File, Metadata};
use std::mem::{size_of, size_of_val};
use std::os::fd::AsRawFd;
use std::os::macos::fs::MetadataExt as DarwinMetadataExt;
use std::os::unix::fs::MetadataExt;

use blake3::{Hash, Hasher};

/// getattrlist(2) defines a nonzero write generation as an equality check on
/// the data of the same object. A writable mapping can make it unavailable.
pub(super) fn data_version(file: &File, meta: &Metadata) -> Option<Hash> {
    let mut request = libc::attrlist {
        bitmapcount: libc::ATTR_BIT_MAP_COUNT,
        reserved: 0,
        commonattr: libc::ATTR_CMN_RETURNED_ATTRS | libc::ATTR_CMN_GEN_COUNT | libc::ATTR_CMN_FSID,
        volattr: 0,
        dirattr: 0,
        fileattr: 0,
        forkattr: 0,
    };
    #[repr(C)]
    struct Version {
        length: u32,
        returned: libc::attribute_set_t,
        fsid: [u32; 2],
        generation: u32,
    }
    // All fields are integers. Each syscall receives the exact size of its buffer.
    let mut version: Version = unsafe { std::mem::zeroed() };
    let read = |request: &mut libc::attrlist, dst, len| unsafe {
        libc::fgetattrlist(
            file.as_raw_fd(),
            std::ptr::from_mut(request).cast(),
            dst,
            len,
            libc::FSOPT_ATTR_CMN_EXTENDED | libc::FSOPT_RETURN_REALDEV,
        )
    };
    if read(
        &mut request,
        std::ptr::from_mut(&mut version).cast(),
        size_of::<Version>(),
    ) != 0
        || version.length as usize != size_of::<Version>()
        || version.returned.commonattr != request.commonattr
        || version.generation == 0
    {
        return None;
    }
    // File IDs are local to a volume. Also bind the mount, birth time and
    // metadata changes so replacements and restored timestamps are distinct.
    request.commonattr = libc::ATTR_CMN_RETURNED_ATTRS;
    request.volattr = libc::ATTR_VOL_INFO | libc::ATTR_VOL_UUID;
    #[repr(C)]
    struct Volume {
        length: u32,
        returned: libc::attribute_set_t,
        uuid: [u8; 16],
    }
    let mut volume: Volume = unsafe { std::mem::zeroed() };
    let len = size_of_val(&volume);
    if read(&mut request, std::ptr::from_mut(&mut volume).cast(), len) != 0
        || volume.length as usize != len
        || volume.returned.volattr != libc::ATTR_VOL_UUID
        || volume.uuid == [0; 16]
    {
        return None;
    }
    let mut key = Hasher::new_derive_key("Ohm native file write generation v1");
    key.update(&volume.uuid);
    for word in version.fsid {
        key.update(&word.to_le_bytes());
    }
    key.update(&meta.dev().to_le_bytes());
    key.update(&meta.ino().to_le_bytes());
    key.update(&meta.st_birthtime().to_le_bytes());
    key.update(&meta.st_birthtime_nsec().to_le_bytes());
    key.update(&meta.ctime().to_le_bytes());
    key.update(&meta.ctime_nsec().to_le_bytes());
    key.update(&meta.len().to_le_bytes());
    key.update(&version.generation.to_le_bytes());
    Some(key.finalize())
}
