use get_size_derive2::GetSize;
#[derive(GetSize)]
struct Conflicting {
    #[get_size(size = 1, size_fn = helper, ignore)]
    value: i32,
}
