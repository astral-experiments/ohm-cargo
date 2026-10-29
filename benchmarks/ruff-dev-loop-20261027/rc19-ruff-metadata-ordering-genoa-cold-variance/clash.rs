#[derive(get_size_derive2::GetSize)]
struct Example {
    #[get_size(size = 1, size_fn = custom_size, ignore)]
    value: u8,
}
