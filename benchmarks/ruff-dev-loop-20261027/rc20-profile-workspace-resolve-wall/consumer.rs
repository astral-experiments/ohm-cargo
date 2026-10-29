use ruff_text_size::{TextRange,TextSize};
fn main(){let r=TextRange::new(TextSize::from(17),TextSize::from(29));println!("{} {} {}",u32::from(r.start()),u32::from(r.end()),u32::from(r.len()));}
