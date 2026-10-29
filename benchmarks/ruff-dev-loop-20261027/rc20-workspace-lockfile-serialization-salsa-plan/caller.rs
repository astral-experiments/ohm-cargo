use ruff_text_size::{TextSize,TextRange};fn main(){let r=TextRange::new(TextSize::from(17u32), TextSize::from(29u32));println!("{} {} {}",u32::from(r.start()),u32::from(r.end()),u32::from(r.len()));}
