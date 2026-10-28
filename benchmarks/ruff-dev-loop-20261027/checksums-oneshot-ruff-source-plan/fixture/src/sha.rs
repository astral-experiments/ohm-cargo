use sha2::{Digest, Sha256 as Sha2_sha256};
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

    pub fn finish(&mut self) -> [u8; 32] {
        self.0.finalize_reset().into()
    }

}
