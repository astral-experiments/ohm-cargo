#![feature(prelude_import)]
//! Derives the `GetSize` trait of [`get-size2`](https://docs.rs/get-size2) for structs and enums.
//!
//! This crate is re-exported by `get-size2` and is meant to be used through its `derive` feature.
//! See [`GetSize`](macro@GetSize) for the attribute reference.
extern crate std;
#[prelude_import]
use std::prelude::rust_2024::*;

use attribute_derive::{Attribute, FromAttr};
use proc_macro::TokenStream;
use quote::{format_ident, quote};

#[attribute(ident = get_size)]
struct StructFieldAttribute {
    #[attribute(conflicts = [size_fn, ignore])]
    size: Option<usize>,
    #[attribute(conflicts = [size, ignore])]
    size_fn: Option<syn::Ident>,
    #[attribute(conflicts = [size, size_fn])]
    ignore: bool,
}
#[allow(clippy :: field_reassign_with_default, remove_unnecessary_else)]
const _: () =
    {
        impl ::attribute_derive::AttributeIdent for StructFieldAttribute {
            const IDENTS: &'static [&'static str] = &["get_size"];
        }
        struct StructFieldAttributePartial {
            size: ::core::prelude::v1::Option<::attribute_derive::parsing::Named<::attribute_derive::parsing::SpannedValue<<Option<usize>
            as ::attribute_derive::parsing::AttributeBase>::Partial>>>,
            size_fn: ::core::prelude::v1::Option<::attribute_derive::parsing::Named<::attribute_derive::parsing::SpannedValue<<Option<syn::Ident>
            as ::attribute_derive::parsing::AttributeBase>::Partial>>>,
            ignore: ::core::prelude::v1::Option<::attribute_derive::parsing::Named<::attribute_derive::parsing::SpannedValue<<bool
            as ::attribute_derive::parsing::AttributeBase>::Partial>>>,
        }
        #[automatically_derived]
        impl ::core::default::Default for StructFieldAttributePartial {
            #[inline]
            fn default() -> StructFieldAttributePartial {
                StructFieldAttributePartial {
                    size: ::core::default::Default::default(),
                    size_fn: ::core::default::Default::default(),
                    ignore: ::core::default::Default::default(),
                }
            }
        }
        impl ::attribute_derive::parsing::AttributeBase for
            StructFieldAttribute {
            type Partial = StructFieldAttributePartial;
        }
        impl ::attribute_derive::parsing::AttributeMeta for
            StructFieldAttribute {
            fn parse_inner(__input:
                    ::attribute_derive::__private::syn::parse::ParseStream)
                -> ::attribute_derive::__private::syn::Result<Self::Partial> {
                let mut __partial = StructFieldAttributePartial::default();
                while !__input.is_empty() {
                    if let ::core::prelude::v1::Some(__field) =
                            <Option<usize> as
                                            ::attribute_derive::parsing::AttributeNamed>::parse_named("size",
                                        __input).map_err(|__error|
                                        {
                                            ::attribute_derive::__private::syn::Error::new(__error.span(),






                                                // Skip all attributes which do not belong to us.

                                                // Make sure it is a list: #[get_size(...)]

                                                // Parse the nested meta: #[get_size(ignore(...))] or #[get_size(ignore)]
                                                // Only handle `ignore`
                                                // Skip unrelated

                                                // Handle the flag case: #[get_size(ignore)]
                                                // Do nothing – valid empty ignore

                                                // Handle the list case: #[get_size(ignore(A, B))]






                                                // Add a bound `T: GetSize` to every type parameter T, unless we ignore it.




                                                // Construct a representation of Rust code as a syntax tree that we can manipulate.

                                                // The name of the struct.

                                                // Extract all generics we shall ignore.
                                                // let ignored = extract_ignored_generics_list(&ast.attrs);

                                                // Add a bound `T: GetSize` to every type parameter T.

                                                // Extract the generics of the struct/enum.

                                                // Traverse the parsed data to generate the individual parts of the function.
                                                // Empty enums are easy to implement.





                                                // Parse all relevant attributes.

                                                // Fields handled by `size` or `ignore` are never read, so they are
                                                // bound to a wildcard to avoid unused variable warnings.











                                                // Fields handled by `size` or `ignore` are never read, so they stay
                                                // out of the pattern and are covered by its `..` rest pattern.








                                                // Build the trait implementation



                                                // Empty structs are easy to implement.


                                                // For newtypes

                                                // Parse all relevant attributes.

                                                // How this field is accessed: by name, or by position for tuple structs. The
                                                // positional counter has to advance even when the field is handled by one of the
                                                // attributes below, otherwise all following fields of a tuple struct would be
                                                // read at the wrong position.





                                                // Build the trait implementation





                                                ::alloc::__export::must_use({
                                                        ::alloc::fmt::format(format_args!("{2}\n\n= help: try `#[get_size(size{0}...{1})]`{0:.0}{1:.0}",
                                                                <Option<usize> as
                                                                    ::attribute_derive::parsing::AttributeNamed>::PREFERRED_OPEN_DELIMITER,
                                                                <Option<usize> as
                                                                    ::attribute_derive::parsing::AttributeNamed>::PREFERRED_CLOSE_DELIMITER,
                                                                __error))
                                                    }))
                                        })? {
                        let __name = __field.name;
                        __partial.size =
                            <Option<usize> as
                                            ::attribute_derive::from_partial::FromPartial<<Option<usize>
                                            as
                                            ::attribute_derive::parsing::AttributeBase>::Partial>>::join(std::mem::take(&mut __partial.size).map(|__v|
                                                __v.value), __field.value,
                                        "`size` is specified multiple times")?.map(|__v|
                                    ::attribute_derive::parsing::Named {
                                        name: __name,
                                        value: __v,
                                    });
                        if __input.is_empty() {
                            return ::core::prelude::v1::Ok(__partial);
                        } else {
                            <::syn::token::Comma as
                                        ::attribute_derive::__private::syn::parse::Parse>::parse(__input)?;
                        };
                        continue;
                    }
                    if let ::core::prelude::v1::Some(__field) =
                            <Option<syn::Ident> as
                                            ::attribute_derive::parsing::AttributeNamed>::parse_named("size_fn",
                                        __input).map_err(|__error|
                                        {
                                            ::attribute_derive::__private::syn::Error::new(__error.span(),
                                                ::alloc::__export::must_use({
                                                        ::alloc::fmt::format(format_args!("{2}\n\n= help: try `#[get_size(size_fn{0}...{1})]`{0:.0}{1:.0}",
                                                                <Option<syn::Ident> as
                                                                    ::attribute_derive::parsing::AttributeNamed>::PREFERRED_OPEN_DELIMITER,
                                                                <Option<syn::Ident> as
                                                                    ::attribute_derive::parsing::AttributeNamed>::PREFERRED_CLOSE_DELIMITER,
                                                                __error))
                                                    }))
                                        })? {
                        let __name = __field.name;
                        __partial.size_fn =
                            <Option<syn::Ident> as
                                            ::attribute_derive::from_partial::FromPartial<<Option<syn::Ident>
                                            as
                                            ::attribute_derive::parsing::AttributeBase>::Partial>>::join(std::mem::take(&mut __partial.size_fn).map(|__v|
                                                __v.value), __field.value,
                                        "`size_fn` is specified multiple times")?.map(|__v|
                                    ::attribute_derive::parsing::Named {
                                        name: __name,
                                        value: __v,
                                    });
                        if __input.is_empty() {
                            return ::core::prelude::v1::Ok(__partial);
                        } else {
                            <::syn::token::Comma as
                                        ::attribute_derive::__private::syn::parse::Parse>::parse(__input)?;
                        };
                        continue;
                    }
                    if let ::core::prelude::v1::Some(__field) =
                            <bool as
                                            ::attribute_derive::parsing::AttributeNamed>::parse_named("ignore",
                                        __input).map_err(|__error|
                                        {
                                            ::attribute_derive::__private::syn::Error::new(__error.span(),
                                                ::alloc::__export::must_use({
                                                        ::alloc::fmt::format(format_args!("{2}\n\n= help: try `#[get_size(ignore{0}...{1})]`{0:.0}{1:.0}",
                                                                <bool as
                                                                    ::attribute_derive::parsing::AttributeNamed>::PREFERRED_OPEN_DELIMITER,
                                                                <bool as
                                                                    ::attribute_derive::parsing::AttributeNamed>::PREFERRED_CLOSE_DELIMITER,
                                                                __error))
                                                    }))
                                        })? {
                        let __name = __field.name;
                        __partial.ignore =
                            <bool as
                                            ::attribute_derive::from_partial::FromPartial<<bool as
                                            ::attribute_derive::parsing::AttributeBase>::Partial>>::join(std::mem::take(&mut __partial.ignore).map(|__v|
                                                __v.value), __field.value,
                                        "`ignore` is specified multiple times")?.map(|__v|
                                    ::attribute_derive::parsing::Named {
                                        name: __name,
                                        value: __v,
                                    });
                        if __input.is_empty() {
                            return ::core::prelude::v1::Ok(__partial);
                        } else {
                            <::syn::token::Comma as
                                        ::attribute_derive::__private::syn::parse::Parse>::parse(__input)?;
                        };
                        continue;
                    }
                    return ::core::prelude::v1::Err(__input.error("supported fields are `size`, `size_fn` and `ignore`"));
                }
                ::core::prelude::v1::Ok(__partial)
            }
        }
        impl ::attribute_derive::__private::syn::parse::Parse for
            StructFieldAttribute {
            fn parse(__input:
                    ::attribute_derive::__private::syn::parse::ParseStream)
                -> ::attribute_derive::__private::syn::Result<Self> {
                <Self as ::attribute_derive::FromAttr>::parse_input(__input)
            }
        }
        impl ::attribute_derive::from_partial::FromPartial<StructFieldAttributePartial>
            for StructFieldAttribute {
            fn from(__partial: StructFieldAttributePartial)
                -> ::attribute_derive::__private::syn::Result<Self> {
                if let (::core::prelude::v1::Some(__a),
                        ::core::prelude::v1::Some(__b)) =
                        (&__partial.size, &__partial.size_fn) {
                    if let ::core::prelude::v1::Some(__joined_span) =
                            __a.error_span().join(__b.error_span()) {
                        return ::core::prelude::v1::Err(::attribute_derive::__private::syn::Error::new(__joined_span,
                                    "`size` conflicts with mutually exclusive `size_fn`"));
                    } else {
                        let mut __error =
                            ::attribute_derive::__private::syn::Error::new(__a.error_span(),
                                "`size` conflicts with mutually exclusive `size_fn`");
                        __error.combine(::attribute_derive::__private::syn::Error::new(__b.error_span(),
                                "`size_fn` conflicts with mutually exclusive `size`"));
                        return ::core::prelude::v1::Err(__error);
                    }
                }
                if let (::core::prelude::v1::Some(__a),
                        ::core::prelude::v1::Some(__b)) =
                        (&__partial.ignore, &__partial.size) {
                    if let ::core::prelude::v1::Some(__joined_span) =
                            __a.error_span().join(__b.error_span()) {
                        return ::core::prelude::v1::Err(::attribute_derive::__private::syn::Error::new(__joined_span,
                                    "`ignore` conflicts with mutually exclusive `size`"));
                    } else {
                        let mut __error =
                            ::attribute_derive::__private::syn::Error::new(__a.error_span(),
                                "`ignore` conflicts with mutually exclusive `size`");
                        __error.combine(::attribute_derive::__private::syn::Error::new(__b.error_span(),
                                "`size` conflicts with mutually exclusive `ignore`"));
                        return ::core::prelude::v1::Err(__error);
                    }
                }
                if let (::core::prelude::v1::Some(__a),
                        ::core::prelude::v1::Some(__b)) =
                        (&__partial.ignore, &__partial.size_fn) {
                    if let ::core::prelude::v1::Some(__joined_span) =
                            __a.error_span().join(__b.error_span()) {
                        return ::core::prelude::v1::Err(::attribute_derive::__private::syn::Error::new(__joined_span,
                                    "`ignore` conflicts with mutually exclusive `size_fn`"));
                    } else {
                        let mut __error =
                            ::attribute_derive::__private::syn::Error::new(__a.error_span(),
                                "`ignore` conflicts with mutually exclusive `size_fn`");
                        __error.combine(::attribute_derive::__private::syn::Error::new(__b.error_span(),
                                "`size_fn` conflicts with mutually exclusive `ignore`"));
                        return ::core::prelude::v1::Err(__error);
                    }
                }
                ::core::prelude::v1::Ok(Self {
                        size: <Option<usize> as
                                    ::attribute_derive::from_partial::FromPartial<<Option<usize>
                                    as
                                    ::attribute_derive::parsing::AttributeBase>::Partial>>::from_option(__partial.size.map(|__v|
                                        __v.value()),
                                &::alloc::__export::must_use({
                                            ::alloc::fmt::format(format_args!("required `size` is not specified\n\n= help: try `#[get_size(size{0}...{1})]`{0:.0}{1:.0}",
                                                    <Option<usize> as
                                                        ::attribute_derive::parsing::AttributeNamed>::PREFERRED_OPEN_DELIMITER,
                                                    <Option<usize> as
                                                        ::attribute_derive::parsing::AttributeNamed>::PREFERRED_CLOSE_DELIMITER))
                                        }))?,
                        size_fn: <Option<syn::Ident> as
                                    ::attribute_derive::from_partial::FromPartial<<Option<syn::Ident>
                                    as
                                    ::attribute_derive::parsing::AttributeBase>::Partial>>::from_option(__partial.size_fn.map(|__v|
                                        __v.value()),
                                &::alloc::__export::must_use({
                                            ::alloc::fmt::format(format_args!("required `size_fn` is not specified\n\n= help: try `#[get_size(size_fn{0}...{1})]`{0:.0}{1:.0}",
                                                    <Option<syn::Ident> as
                                                        ::attribute_derive::parsing::AttributeNamed>::PREFERRED_OPEN_DELIMITER,
                                                    <Option<syn::Ident> as
                                                        ::attribute_derive::parsing::AttributeNamed>::PREFERRED_CLOSE_DELIMITER))
                                        }))?,
                        ignore: <bool as
                                    ::attribute_derive::from_partial::FromPartial<<bool as
                                    ::attribute_derive::parsing::AttributeBase>::Partial>>::from_option(__partial.ignore.map(|__v|
                                        __v.value()),
                                &::alloc::__export::must_use({
                                            ::alloc::fmt::format(format_args!("required `ignore` is not specified\n\n= help: try `#[get_size(ignore{0}...{1})]`{0:.0}{1:.0}",
                                                    <bool as
                                                        ::attribute_derive::parsing::AttributeNamed>::PREFERRED_OPEN_DELIMITER,
                                                    <bool as
                                                        ::attribute_derive::parsing::AttributeNamed>::PREFERRED_CLOSE_DELIMITER))
                                        }))?,
                    })
            }
            fn from_option(__partial:
                    ::core::prelude::v1::Option<StructFieldAttributePartial>,
                _: &str) -> ::attribute_derive::__private::syn::Result<Self> {
                <Self as
                        ::attribute_derive::from_partial::FromPartial<StructFieldAttributePartial>>::from(__partial.unwrap_or_default())
            }
            fn join(__first:
                    ::core::prelude::v1::Option<::attribute_derive::parsing::SpannedValue<StructFieldAttributePartial>>,
                __second:
                    ::attribute_derive::parsing::SpannedValue<StructFieldAttributePartial>,
                _: &str)
                ->
                    ::attribute_derive::__private::syn::Result<::core::prelude::v1::Option<::attribute_derive::parsing::SpannedValue<StructFieldAttributePartial>>> {
                let mut __first = __first.unwrap_or_default().value;
                let __span = __second.span;
                let __second = __second.value;
                if let ::core::prelude::v1::Some(__second) = __second.size {
                    let (__first_name, __first_value) =
                        if let ::core::prelude::v1::Some(__first) =
                                ::std::mem::take(&mut __first.size) {
                            (::core::prelude::v1::Some(__first.name),
                                ::core::prelude::v1::Some(__first.value))
                        } else {
                            (::core::prelude::v1::None, ::core::prelude::v1::None)
                        };
                    let __name = __first_name.unwrap_or(__second.name);
                    let __second_value = __second.value;
                    __first.size =
                        <Option<usize> as
                                        ::attribute_derive::from_partial::FromPartial<<Option<usize>
                                        as
                                        ::attribute_derive::parsing::AttributeBase>::Partial>>::join(__first_value,
                                    __second_value,
                                    "`size` is specified multiple times")?.map(|__v|
                                ::attribute_derive::parsing::Named {
                                    name: __name,
                                    value: __v,
                                });
                };
                if let ::core::prelude::v1::Some(__second) = __second.size_fn
                    {
                    let (__first_name, __first_value) =
                        if let ::core::prelude::v1::Some(__first) =
                                ::std::mem::take(&mut __first.size_fn) {
                            (::core::prelude::v1::Some(__first.name),
                                ::core::prelude::v1::Some(__first.value))
                        } else {
                            (::core::prelude::v1::None, ::core::prelude::v1::None)
                        };
                    let __name = __first_name.unwrap_or(__second.name);
                    let __second_value = __second.value;
                    __first.size_fn =
                        <Option<syn::Ident> as
                                        ::attribute_derive::from_partial::FromPartial<<Option<syn::Ident>
                                        as
                                        ::attribute_derive::parsing::AttributeBase>::Partial>>::join(__first_value,
                                    __second_value,
                                    "`size_fn` is specified multiple times")?.map(|__v|
                                ::attribute_derive::parsing::Named {
                                    name: __name,
                                    value: __v,
                                });
                };
                if let ::core::prelude::v1::Some(__second) = __second.ignore {
                    let (__first_name, __first_value) =
                        if let ::core::prelude::v1::Some(__first) =
                                ::std::mem::take(&mut __first.ignore) {
                            (::core::prelude::v1::Some(__first.name),
                                ::core::prelude::v1::Some(__first.value))
                        } else {
                            (::core::prelude::v1::None, ::core::prelude::v1::None)
                        };
                    let __name = __first_name.unwrap_or(__second.name);
                    let __second_value = __second.value;
                    __first.ignore =
                        <bool as
                                        ::attribute_derive::from_partial::FromPartial<<bool as
                                        ::attribute_derive::parsing::AttributeBase>::Partial>>::join(__first_value,
                                    __second_value,
                                    "`ignore` is specified multiple times")?.map(|__v|
                                ::attribute_derive::parsing::Named {
                                    name: __name,
                                    value: __v,
                                });
                };
                ::core::prelude::v1::Ok(::core::prelude::v1::Some(::attribute_derive::parsing::SpannedValue {
                            span: __span,
                            value: __first,
                        }))
            }
        }
    };
#[automatically_derived]
impl ::core::default::Default for StructFieldAttribute {
    #[inline]
    fn default() -> StructFieldAttribute {
        StructFieldAttribute {
            size: ::core::default::Default::default(),
            size_fn: ::core::default::Default::default(),
            ignore: ::core::default::Default::default(),
        }
    }
}
#[automatically_derived]
impl ::core::fmt::Debug for StructFieldAttribute {
    #[inline]
    fn fmt(&self, f: &mut ::core::fmt::Formatter) -> ::core::fmt::Result {
        ::core::fmt::Formatter::debug_struct_field3_finish(f,
            "StructFieldAttribute", "size", &self.size, "size_fn",
            &self.size_fn, "ignore", &&self.ignore)
    }
}
fn extract_ignored_generics_list(list: &Vec<syn::Attribute>)
    -> Vec<syn::PathSegment> {
    let mut collection = Vec::new();
    for attr in list {
        let mut list = extract_ignored_generics(attr);
        collection.append(&mut list);
    }
    collection
}
fn extract_ignored_generics(attr: &syn::Attribute) -> Vec<syn::PathSegment> {
    let mut collection = Vec::new();
    if !attr.meta.path().is_ident("get_size") { return collection; }
    let Ok(list) = attr.meta.require_list() else { return collection; };
    let _ =
        list.parse_nested_meta(|meta|
                {
                    if !meta.path.is_ident("ignore") { return Ok(()); }
                    if meta.input.is_empty() { return Ok(()); }
                    meta.parse_nested_meta(|meta|
                                {
                                    for segment in meta.path.segments {
                                        collection.push(segment);
                                    }
                                    Ok(())
                                })?;
                    Ok(())
                });
    collection
}
fn collect_all_ignored_generics(ast: &syn::DeriveInput)
    -> Vec<syn::PathSegment> {
    let mut ignored = extract_ignored_generics_list(&ast.attrs);
    match &ast.data {
        syn::Data::Struct(data_struct) => {
            for field in &data_struct.fields {
                ignored.extend(extract_ignored_generics_list(&field.attrs));
            }
        }
        syn::Data::Enum(data_enum) => {
            for variant in &data_enum.variants {
                ignored.extend(extract_ignored_generics_list(&variant.attrs));
                for field in &variant.fields {
                    ignored.extend(extract_ignored_generics_list(&field.attrs));
                }
            }
        }
        syn::Data::Union(_) => {}
    }
    ignored
}
fn add_trait_bounds(mut generics: syn::Generics,
    ignored: &Vec<syn::PathSegment>) -> syn::Generics {
    for param in &mut generics.params {
        if let syn::GenericParam::Type(type_param) = param {
            let mut found = false;
            for ignored in ignored {
                if ignored.ident == type_param.ident { found = true; break; }
            }
            if found { continue; }
            type_param.bounds.push(::syn::__private::parse_quote({
                        let mut _s = ::quote::__private::TokenStream::new();
                        ::quote::__private::push_colon2(&mut _s);
                        ::quote::__private::push_ident(&mut _s, "get_size2");
                        ::quote::__private::push_colon2(&mut _s);
                        ::quote::__private::push_ident(&mut _s, "GetSize");
                        _s
                    }));
        }
    }
    generics
}
#[doc =
"Derives the [`GetSize`] trait for structs and enums.\n\nAvailable through the `derive` feature of [`get-size2`](https://docs.rs/get-size2):\n\n```toml\nget-size2 = { version = \"^0.10\", features = [\"derive\"] }\n```\n\nThe generated [`get_heap_size`] implementation calls [`get_heap_size`] on every field and sums up the results, which means every field type must implement [`GetSize`] as well, unless it is handled by one of the [attributes](#attributes) below. Shared ownership is deduplicated, since the generated implementation threads a tracker through all fields.\n\nUnions are not supported and produce a compile error.\n\n# Examples\n\nStructs, tuple structs and enums are all supported:\n\n```rust\nuse get_size2::GetSize;\n\n#[derive(GetSize)]\nstruct Data {\n    name: String,\n    id: u64,\n}\n\n#[derive(GetSize)]\nstruct Wrapper(String);\n\n#[derive(GetSize)]\nenum Message {\n    Empty,\n    Text(String),\n    Pair { left: String, right: String },\n}\n\n#[derive(GetSize)]\nenum Level {\n    Low = 0,\n    High = 1,\n}\n\nlet data = Data { name: \"Hello\".into(), id: 123 };\nassert_eq!(data.get_heap_size(), 5);\n\nassert_eq!(Wrapper(\"Hello\".into()).get_heap_size(), 5);\n\nassert_eq!(Message::Empty.get_heap_size(), 0);\nassert_eq!(Message::Text(\"Hello\".into()).get_heap_size(), 5);\nassert_eq!(\n    Message::Pair { left: \"Hello\".into(), right: \"world\".into() }.get_heap_size(),\n    5 + 5\n);\n\nassert_eq!(Level::High.get_heap_size(), 0);\n```\n\nGenerics work too. The generated implementation requires every generic type to implement [`GetSize`], which [can be changed](#ignoring-generic-types):\n\n```rust\nuse get_size2::GetSize;\n\n#[derive(GetSize)]\nstruct Pair<A, B> {\n    first: A,\n    second: B,\n}\n\nlet pair: Pair<String, u64> = Pair { first: \"Hello\".into(), second: 123 };\nassert_eq!(pair.get_heap_size(), 5);\n```\n\n# Borrowed fields\n\nFields holding a reference or a raw pointer need no attribute, but they always contribute `0`, no matter how much the target allocates. Borrowed bytes belong to whoever owns them, so counting them here would report them twice. This holds for every reference, including those to unsized targets such as `&str`, `&[T]` and `&dyn Trait`:\n\n```rust\nuse get_size2::GetSize;\n\n#[derive(GetSize)]\nstruct Borrowing<\'a> {\n    id: u64,\n    name: &\'a str,\n    values: &\'a [String],\n}\n\nlet name = String::from(\"Hello\");\nlet values = vec![String::from(\"world\")];\n\nlet borrowing = Borrowing { id: 1, name: &name, values: &values };\n\n// The 5 and 5 bytes belong to `name` and `values`, so this struct owns nothing.\nassert_eq!(borrowing.get_heap_size(), 0);\n```\n\nUse `size_fn` for the rare case of a struct which is effectively the owner of the data it points at, for example after leaking an allocation or when the target lives in an arena:\n\n```rust\nuse get_size2::GetSize;\n\n#[derive(GetSize)]\nstruct Owning {\n    #[get_size(size_fn = str_len)]\n    leaked: &\'static str,\n}\n\n// The generated code passes a reference to the field, hence the double reference.\nfn str_len(value: &&\'static str) -> usize {\n    value.len()\n}\n\nlet owning = Owning { leaked: String::from(\"Hello\").leak() };\nassert_eq!(owning.get_heap_size(), 5);\n```\n\n# Attributes\n\nIf a field\'s type does not implement [`GetSize`], the `#[get_size(...)]` attribute offers three ways out, plus a struct or enum level escape hatch for generics:\n\n| Attribute | Position | Effect |\n| --------- | -------- | ------ |\n| `#[get_size(ignore)]` | Field | Skips the field, contributing `0` |\n| `#[get_size(size = 1024)]` | Field | Accounts the field with a fixed number of bytes |\n| `#[get_size(size_fn = my_helper)]` | Field | Calls `my_helper(&field)` to determine the heap size |\n| `#[get_size(ignore(A, B))]` | Struct or enum | Drops the [`GetSize`] bound on the listed generic types |\n\nThe three field attributes work on the fields of structs, of tuple structs and of enum variants alike.\n\n## Ignoring fields\n\nThe idiomatic use is a shared allocation which is already accounted for elsewhere, when the [tracker](https://docs.rs/get-size2/latest/get_size2/trait.GetSizeTracker.html) based deduplication is not what you want:\n\n```rust\nuse std::sync::Arc;\nuse get_size2::GetSize;\n\n#[derive(GetSize)]\nstruct PrimaryStore {\n    id: u64,\n    shared_data: Arc<Vec<u8>>,\n}\n\n#[derive(GetSize)]\nstruct SecondaryStore {\n    id: u64,\n    #[get_size(ignore)]\n    shared_data: Arc<Vec<u8>>,\n}\n\nlet shared_data = Arc::new(Vec::with_capacity(1024));\n\nlet primary = PrimaryStore { id: 1, shared_data: Arc::clone(&shared_data) };\nlet secondary = SecondaryStore { id: 2, shared_data };\n\n// The `Arc` also stores the `Vec`\'s stack data on the heap.\nassert_eq!(primary.get_heap_size(), Vec::<u8>::get_stack_size() + 1024);\nassert_eq!(secondary.get_heap_size(), 0);\n```\n\nIt also works as a band aid for a field whose type does not implement [`GetSize`], but the result will then be too low unless that type really owns no heap memory. Prefer `size` or `size_fn` in that case.\n\n```rust\nuse get_size2::GetSize;\n\n// Does not implement GetSize!\nstruct External {\n    value: String,\n}\n\n#[derive(GetSize)]\nstruct Data {\n    name: String,\n    #[get_size(ignore)]\n    external: External,\n}\n\nlet data = Data {\n    name: \"Adam\".into(),\n    external: External { value: \"Hello world!\".into() },\n};\n\n// The 12 bytes owned by `external` are missing from the result.\nassert_eq!(data.get_heap_size(), 4);\n```\n\n## Returning a fixed size\n\nFor external types which always allocate the same number of bytes:\n\n```rust\nuse get_size2::GetSize;\n# struct Buffer1024 {}\n#\n# impl Buffer1024 {\n#   fn new() -> Self {\n#      Self {}\n#   }\n# }\n\n#[derive(GetSize)]\nstruct Data {\n    id: u64,\n    #[get_size(size = 1024)]\n    buffer: Buffer1024, // Always allocates exactly 1KB on the heap.\n}\n\nlet data = Data { id: 1, buffer: Buffer1024::new() };\nassert_eq!(data.get_heap_size(), 1024);\n```\n\n## Using a helper function\n\nIf the heap size of an external type can be derived from its public API, `size_fn` names a function to call. Unlike in other crates the function name is given directly, not as a string. This is particularly useful for a helper which is generic over a trait, and covers several types at once.\n\nAlternatively, wrap the type in a newtype and implement [`GetSize`] for that.\n\n```rust\nuse get_size2::GetSize;\n# type ExternalVecAlike<T> = Vec<T>;\n\n#[derive(GetSize)]\nstruct Data {\n    id: u64,\n    #[get_size(size_fn = vec_alike_helper)]\n    buffer: ExternalVecAlike<u8>,\n}\n\n// NOTE: We assume that slice.len() == slice.capacity()\nfn vec_alike_helper<V, T>(slice: &V) -> usize\nwhere\n    V: AsRef<[T]>,\n{\n    std::mem::size_of::<T>() * slice.as_ref().len()\n}\n\nlet data = Data { id: 1, buffer: vec![0u8; 512].into() };\nassert_eq!(data.get_heap_size(), 512);\n```\n\n## Ignoring generic types\n\nA generic used only by ignored or helper handled fields still gets a [`GetSize`] bound, which would make the implementation unusable. List those generics in a struct level `ignore` to drop their bounds:\n\n```rust\nuse get_size2::GetSize;\n\n#[derive(GetSize)]\n#[get_size(ignore(B, C, D))]\nstruct Data<A, B, C, D> {\n    value1: A,\n    #[get_size(size = 100)]\n    value2: B,\n    #[get_size(size_fn = helper)]\n    value3: C,\n    #[get_size(ignore)]\n    value4: D,\n}\n\n// Does not implement GetSize.\nstruct NoGetSize {}\n\nfn helper<C>(_value: &C) -> usize {\n    50\n}\n\nlet data: Data<String, NoGetSize, NoGetSize, u64> = Data {\n    value1: \"Hello\".into(),\n    value2: NoGetSize {},\n    value3: NoGetSize {},\n    value4: 123,\n};\n\nassert_eq!(data.get_heap_size(), 5 + 100 + 50);\n```\n\n# Errors\n\nThe macro reports a compile error when it is used on a union, or when conflicting attributes such as `size` and `ignore` are combined on the same field. A field whose type does not implement [`GetSize`] and which is not covered by an attribute also fails to compile.\n\n[`GetSize`]: https://docs.rs/get-size2/latest/get_size2/trait.GetSize.html\n[`get_heap_size`]: https://docs.rs/get-size2/latest/get_size2/trait.GetSize.html#method.get_heap_size\n"]
#[proc_macro_derive(GetSize, attributes(get_size))]
pub fn derive_get_size(input: TokenStream) -> TokenStream {
    match derive_get_size_impl(input) {
        Ok(tokens) => tokens,
        Err(err) => err.to_compile_error().into(),
    }
}
#[expect(clippy::too_many_lines, reason = "Needs refactoring")]
fn derive_get_size_impl(input: TokenStream) -> syn::Result<TokenStream> {
    let ast: syn::DeriveInput = syn::parse(input)?;
    let name = &ast.ident;
    let ignored = collect_all_ignored_generics(&ast);
    let generics = add_trait_bounds(ast.generics, &ignored);
    let (impl_generics, ty_generics, where_clause) =
        generics.split_for_impl();
    match ast.data {
        syn::Data::Enum(data_enum) => {
            if data_enum.variants.is_empty() {
                let generated =
                    {
                        let mut _s = ::quote::__private::TokenStream::new();
                        ::quote::__private::push_ident(&mut _s, "impl");
                        ::quote::__private::push_colon2(&mut _s);
                        ::quote::__private::push_ident(&mut _s, "get_size2");
                        ::quote::__private::push_colon2(&mut _s);
                        ::quote::__private::push_ident(&mut _s, "GetSize");
                        ::quote::__private::push_ident(&mut _s, "for");
                        ::quote::ToTokens::to_tokens(&name, &mut _s);
                        ::quote::__private::push_group(&mut _s,
                            ::quote::__private::Delimiter::Brace,
                            ::quote::__private::TokenStream::new());
                        _s
                    };
                return Ok(generated.into());
            }
            let mut cmds = Vec::with_capacity(data_enum.variants.len());
            for variant in data_enum.variants {
                let ident = &variant.ident;
                match &variant.fields {
                    syn::Fields::Unnamed(unnamed_fields) => {
                        let num_fields = unnamed_fields.unnamed.len();
                        let mut field_idents = Vec::with_capacity(num_fields);
                        let mut field_cmds = Vec::with_capacity(num_fields);
                        for (i, field) in unnamed_fields.unnamed.iter().enumerate()
                            {
                            let attr =
                                StructFieldAttribute::from_attributes(&field.attrs).map_err(|err|
                                            syn::Error::new_spanned(field, err.to_string()))?;
                            if let Some(size) = attr.size {
                                field_idents.push({
                                        let mut _s = ::quote::__private::TokenStream::new();
                                        ::quote::__private::push_underscore(&mut _s);
                                        _s
                                    });
                                field_cmds.push({
                                        let mut _s = ::quote::__private::TokenStream::new();
                                        ::quote::__private::push_ident(&mut _s, "total");
                                        ::quote::__private::push_add_eq(&mut _s);
                                        ::quote::ToTokens::to_tokens(&size, &mut _s);
                                        ::quote::__private::push_semi(&mut _s);
                                        _s
                                    });
                                continue;
                            } else if attr.ignore {
                                field_idents.push({
                                        let mut _s = ::quote::__private::TokenStream::new();
                                        ::quote::__private::push_underscore(&mut _s);
                                        _s
                                    });
                                continue;
                            }
                            let field_ident =
                                ::quote::__private::mk_ident(&::alloc::__export::must_use({
                                                ::alloc::fmt::format(format_args!("v{0}", i))
                                            }), ::quote::__private::Option::None);
                            if let Some(size_fn) = attr.size_fn {
                                field_cmds.push({
                                        let mut _s = ::quote::__private::TokenStream::new();
                                        ::quote::__private::push_ident(&mut _s, "total");
                                        ::quote::__private::push_add_eq(&mut _s);
                                        ::quote::ToTokens::to_tokens(&size_fn, &mut _s);
                                        ::quote::__private::push_group(&mut _s,
                                            ::quote::__private::Delimiter::Parenthesis,
                                            {
                                                let mut _s = ::quote::__private::TokenStream::new();
                                                ::quote::ToTokens::to_tokens(&field_ident, &mut _s);
                                                _s
                                            });
                                        ::quote::__private::push_semi(&mut _s);
                                        _s
                                    });
                            } else {
                                field_cmds.push({
                                        let mut _s = ::quote::__private::TokenStream::new();
                                        ::quote::__private::push_ident(&mut _s, "let");
                                        ::quote::__private::push_group(&mut _s,
                                            ::quote::__private::Delimiter::Parenthesis,
                                            {
                                                let mut _s = ::quote::__private::TokenStream::new();
                                                ::quote::__private::push_ident(&mut _s, "total_add");
                                                ::quote::__private::push_comma(&mut _s);
                                                ::quote::__private::push_ident(&mut _s, "tracker");
                                                _s
                                            });
                                        ::quote::__private::push_eq(&mut _s);
                                        ::quote::__private::push_colon2(&mut _s);
                                        ::quote::__private::push_ident(&mut _s, "get_size2");
                                        ::quote::__private::push_colon2(&mut _s);
                                        ::quote::__private::push_ident(&mut _s, "GetSize");
                                        ::quote::__private::push_colon2(&mut _s);
                                        ::quote::__private::push_ident(&mut _s,
                                            "get_heap_size_with_tracker");
                                        ::quote::__private::push_group(&mut _s,
                                            ::quote::__private::Delimiter::Parenthesis,
                                            {
                                                let mut _s = ::quote::__private::TokenStream::new();
                                                ::quote::ToTokens::to_tokens(&field_ident, &mut _s);
                                                ::quote::__private::push_comma(&mut _s);
                                                ::quote::__private::push_ident(&mut _s, "tracker");
                                                _s
                                            });
                                        ::quote::__private::push_semi(&mut _s);
                                        ::quote::__private::push_ident(&mut _s, "total");
                                        ::quote::__private::push_add_eq(&mut _s);
                                        ::quote::__private::push_ident(&mut _s, "total_add");
                                        ::quote::__private::push_semi(&mut _s);
                                        _s
                                    });
                            }
                            field_idents.push({
                                    let mut _s = ::quote::__private::TokenStream::new();
                                    ::quote::ToTokens::to_tokens(&field_ident, &mut _s);
                                    _s
                                });
                        }
                        cmds.push({
                                let mut _s = ::quote::__private::TokenStream::new();
                                ::quote::__private::push_ident(&mut _s, "Self");
                                ::quote::__private::push_colon2(&mut _s);
                                ::quote::ToTokens::to_tokens(&ident, &mut _s);
                                ::quote::__private::push_group(&mut _s,
                                    ::quote::__private::Delimiter::Parenthesis,
                                    {
                                        let mut _s = ::quote::__private::TokenStream::new();
                                        {
                                            use ::quote::__private::ext::*;
                                            let has_iter = ::quote::__private::HasIterator::<false>;
                                            #[allow(unused_mut)]
                                            let (mut field_idents, i) = field_idents.quote_into_iter();
                                            let has_iter = has_iter | i;
                                            <_ as
                                                    ::quote::__private::CheckHasIterator<true>>::check(has_iter);
                                            while true {
                                                let field_idents =
                                                    match field_idents.next() {
                                                        Some(_x) => ::quote::__private::RepInterp(_x),
                                                        None => break,
                                                    };
                                                ::quote::ToTokens::to_tokens(&field_idents, &mut _s);
                                                ::quote::__private::push_comma(&mut _s);
                                            }
                                        }
                                        _s
                                    });
                                ::quote::__private::push_fat_arrow(&mut _s);
                                ::quote::__private::push_group(&mut _s,
                                    ::quote::__private::Delimiter::Brace,
                                    {
                                        let mut _s = ::quote::__private::TokenStream::new();
                                        ::quote::__private::push_ident(&mut _s, "let");
                                        ::quote::__private::push_ident(&mut _s, "mut");
                                        ::quote::__private::push_ident(&mut _s, "total");
                                        ::quote::__private::push_eq(&mut _s);
                                        ::quote::__private::parse(&mut _s, "0");
                                        ::quote::__private::push_semi(&mut _s);
                                        {
                                            use ::quote::__private::ext::*;
                                            let has_iter = ::quote::__private::HasIterator::<false>;
                                            #[allow(unused_mut)]
                                            let (mut field_cmds, i) = field_cmds.quote_into_iter();
                                            let has_iter = has_iter | i;
                                            <_ as
                                                    ::quote::__private::CheckHasIterator<true>>::check(has_iter);
                                            while true {
                                                let field_cmds =
                                                    match field_cmds.next() {
                                                        Some(_x) => ::quote::__private::RepInterp(_x),
                                                        None => break,
                                                    };
                                                ::quote::ToTokens::to_tokens(&field_cmds, &mut _s);
                                            }
                                        }
                                        ::quote::__private::push_semi(&mut _s);
                                        ::quote::__private::push_group(&mut _s,
                                            ::quote::__private::Delimiter::Parenthesis,
                                            {
                                                let mut _s = ::quote::__private::TokenStream::new();
                                                ::quote::__private::push_ident(&mut _s, "total");
                                                ::quote::__private::push_comma(&mut _s);
                                                ::quote::__private::push_ident(&mut _s, "tracker");
                                                _s
                                            });
                                        _s
                                    });
                                _s
                            });
                    }
                    syn::Fields::Named(named_fields) => {
                        let mut field_idents = Vec::new();
                        let mut field_cmds = Vec::new();
                        let mut skipped_field = false;
                        for field in &named_fields.named {
                            let field_ident =
                                field.ident.as_ref().ok_or_else(||
                                            {
                                                syn::Error::new_spanned(field, "Expected named field")
                                            })?;
                            let attr =
                                StructFieldAttribute::from_attributes(&field.attrs).map_err(|err|
                                            syn::Error::new_spanned(field, err.to_string()))?;
                            if let Some(size) = attr.size {
                                skipped_field = true;
                                field_cmds.push({
                                        let mut _s = ::quote::__private::TokenStream::new();
                                        ::quote::__private::push_ident(&mut _s, "total");
                                        ::quote::__private::push_add_eq(&mut _s);
                                        ::quote::ToTokens::to_tokens(&size, &mut _s);
                                        ::quote::__private::push_semi(&mut _s);
                                        _s
                                    });
                                continue;
                            } else if attr.ignore { skipped_field = true; continue; }
                            field_idents.push(field_ident);
                            if let Some(size_fn) = attr.size_fn {
                                field_cmds.push({
                                        let mut _s = ::quote::__private::TokenStream::new();
                                        ::quote::__private::push_ident(&mut _s, "total");
                                        ::quote::__private::push_add_eq(&mut _s);
                                        ::quote::ToTokens::to_tokens(&size_fn, &mut _s);
                                        ::quote::__private::push_group(&mut _s,
                                            ::quote::__private::Delimiter::Parenthesis,
                                            {
                                                let mut _s = ::quote::__private::TokenStream::new();
                                                ::quote::ToTokens::to_tokens(&field_ident, &mut _s);
                                                _s
                                            });
                                        ::quote::__private::push_semi(&mut _s);
                                        _s
                                    });
                            } else {
                                field_cmds.push({
                                        let mut _s = ::quote::__private::TokenStream::new();
                                        ::quote::__private::push_ident(&mut _s, "let");
                                        ::quote::__private::push_group(&mut _s,
                                            ::quote::__private::Delimiter::Parenthesis,
                                            {
                                                let mut _s = ::quote::__private::TokenStream::new();
                                                ::quote::__private::push_ident(&mut _s, "total_add");
                                                ::quote::__private::push_comma(&mut _s);
                                                ::quote::__private::push_ident(&mut _s, "tracker");
                                                _s
                                            });
                                        ::quote::__private::push_eq(&mut _s);
                                        ::quote::__private::push_colon2(&mut _s);
                                        ::quote::__private::push_ident(&mut _s, "get_size2");
                                        ::quote::__private::push_colon2(&mut _s);
                                        ::quote::__private::push_ident(&mut _s, "GetSize");
                                        ::quote::__private::push_colon2(&mut _s);
                                        ::quote::__private::push_ident(&mut _s,
                                            "get_heap_size_with_tracker");
                                        ::quote::__private::push_group(&mut _s,
                                            ::quote::__private::Delimiter::Parenthesis,
                                            {
                                                let mut _s = ::quote::__private::TokenStream::new();
                                                ::quote::ToTokens::to_tokens(&field_ident, &mut _s);
                                                ::quote::__private::push_comma(&mut _s);
                                                ::quote::__private::push_ident(&mut _s, "tracker");
                                                _s
                                            });
                                        ::quote::__private::push_semi(&mut _s);
                                        ::quote::__private::push_ident(&mut _s, "total");
                                        ::quote::__private::push_add_eq(&mut _s);
                                        ::quote::__private::push_ident(&mut _s, "total_add");
                                        ::quote::__private::push_semi(&mut _s);
                                        _s
                                    });
                            }
                        }
                        let pattern =
                            if skipped_field {
                                {
                                    let mut _s = ::quote::__private::TokenStream::new();
                                    ::quote::__private::push_ident(&mut _s, "Self");
                                    ::quote::__private::push_colon2(&mut _s);
                                    ::quote::ToTokens::to_tokens(&ident, &mut _s);
                                    ::quote::__private::push_group(&mut _s,
                                        ::quote::__private::Delimiter::Brace,
                                        {
                                            let mut _s = ::quote::__private::TokenStream::new();
                                            {
                                                use ::quote::__private::ext::*;
                                                let has_iter = ::quote::__private::HasIterator::<false>;
                                                #[allow(unused_mut)]
                                                let (mut field_idents, i) = field_idents.quote_into_iter();
                                                let has_iter = has_iter | i;
                                                <_ as
                                                        ::quote::__private::CheckHasIterator<true>>::check(has_iter);
                                                while true {
                                                    let field_idents =
                                                        match field_idents.next() {
                                                            Some(_x) => ::quote::__private::RepInterp(_x),
                                                            None => break,
                                                        };
                                                    ::quote::ToTokens::to_tokens(&field_idents, &mut _s);
                                                    ::quote::__private::push_comma(&mut _s);
                                                }
                                            }
                                            ::quote::__private::push_dot2(&mut _s);
                                            _s
                                        });
                                    _s
                                }
                            } else {
                                {
                                    let mut _s = ::quote::__private::TokenStream::new();
                                    ::quote::__private::push_ident(&mut _s, "Self");
                                    ::quote::__private::push_colon2(&mut _s);
                                    ::quote::ToTokens::to_tokens(&ident, &mut _s);
                                    ::quote::__private::push_group(&mut _s,
                                        ::quote::__private::Delimiter::Brace,
                                        {
                                            let mut _s = ::quote::__private::TokenStream::new();
                                            {
                                                use ::quote::__private::ext::*;
                                                let has_iter = ::quote::__private::HasIterator::<false>;
                                                #[allow(unused_mut)]
                                                let (mut field_idents, i) = field_idents.quote_into_iter();
                                                let has_iter = has_iter | i;
                                                <_ as
                                                        ::quote::__private::CheckHasIterator<true>>::check(has_iter);
                                                while true {
                                                    let field_idents =
                                                        match field_idents.next() {
                                                            Some(_x) => ::quote::__private::RepInterp(_x),
                                                            None => break,
                                                        };
                                                    ::quote::ToTokens::to_tokens(&field_idents, &mut _s);
                                                    ::quote::__private::push_comma(&mut _s);
                                                }
                                            }
                                            _s
                                        });
                                    _s
                                }
                            };
                        cmds.push({
                                let mut _s = ::quote::__private::TokenStream::new();
                                ::quote::ToTokens::to_tokens(&pattern, &mut _s);
                                ::quote::__private::push_fat_arrow(&mut _s);
                                ::quote::__private::push_group(&mut _s,
                                    ::quote::__private::Delimiter::Brace,
                                    {
                                        let mut _s = ::quote::__private::TokenStream::new();
                                        ::quote::__private::push_ident(&mut _s, "let");
                                        ::quote::__private::push_ident(&mut _s, "mut");
                                        ::quote::__private::push_ident(&mut _s, "total");
                                        ::quote::__private::push_eq(&mut _s);
                                        ::quote::__private::parse(&mut _s, "0");
                                        ::quote::__private::push_semi(&mut _s);
                                        {
                                            use ::quote::__private::ext::*;
                                            let has_iter = ::quote::__private::HasIterator::<false>;
                                            #[allow(unused_mut)]
                                            let (mut field_cmds, i) = field_cmds.quote_into_iter();
                                            let has_iter = has_iter | i;
                                            <_ as
                                                    ::quote::__private::CheckHasIterator<true>>::check(has_iter);
                                            while true {
                                                let field_cmds =
                                                    match field_cmds.next() {
                                                        Some(_x) => ::quote::__private::RepInterp(_x),
                                                        None => break,
                                                    };
                                                ::quote::ToTokens::to_tokens(&field_cmds, &mut _s);
                                            }
                                        }
                                        ::quote::__private::push_group(&mut _s,
                                            ::quote::__private::Delimiter::Parenthesis,
                                            {
                                                let mut _s = ::quote::__private::TokenStream::new();
                                                ::quote::__private::push_ident(&mut _s, "total");
                                                ::quote::__private::push_comma(&mut _s);
                                                ::quote::__private::push_ident(&mut _s, "tracker");
                                                _s
                                            });
                                        _s
                                    });
                                _s
                            });
                    }
                    syn::Fields::Unit => {
                        cmds.push({
                                let mut _s = ::quote::__private::TokenStream::new();
                                ::quote::__private::push_ident(&mut _s, "Self");
                                ::quote::__private::push_colon2(&mut _s);
                                ::quote::ToTokens::to_tokens(&ident, &mut _s);
                                ::quote::__private::push_fat_arrow(&mut _s);
                                ::quote::__private::push_group(&mut _s,
                                    ::quote::__private::Delimiter::Parenthesis,
                                    {
                                        let mut _s = ::quote::__private::TokenStream::new();
                                        ::quote::__private::parse(&mut _s, "0");
                                        ::quote::__private::push_comma(&mut _s);
                                        ::quote::__private::push_ident(&mut _s, "tracker");
                                        _s
                                    });
                                ::quote::__private::push_comma(&mut _s);
                                _s
                            });
                    }
                }
            }
            let generated =
                {
                    let mut _s = ::quote::__private::TokenStream::new();
                    ::quote::__private::push_ident(&mut _s, "impl");
                    ::quote::ToTokens::to_tokens(&impl_generics, &mut _s);
                    ::quote::__private::push_colon2(&mut _s);
                    ::quote::__private::push_ident(&mut _s, "get_size2");
                    ::quote::__private::push_colon2(&mut _s);
                    ::quote::__private::push_ident(&mut _s, "GetSize");
                    ::quote::__private::push_ident(&mut _s, "for");
                    ::quote::ToTokens::to_tokens(&name, &mut _s);
                    ::quote::ToTokens::to_tokens(&ty_generics, &mut _s);
                    ::quote::ToTokens::to_tokens(&where_clause, &mut _s);
                    ::quote::__private::push_group(&mut _s,
                        ::quote::__private::Delimiter::Brace,
                        {
                            let mut _s = ::quote::__private::TokenStream::new();
                            ::quote::__private::push_ident(&mut _s, "fn");
                            ::quote::__private::push_ident(&mut _s, "get_heap_size");
                            ::quote::__private::push_group(&mut _s,
                                ::quote::__private::Delimiter::Parenthesis,
                                {
                                    let mut _s = ::quote::__private::TokenStream::new();
                                    ::quote::__private::push_and(&mut _s);
                                    ::quote::__private::push_ident(&mut _s, "self");
                                    _s
                                });
                            ::quote::__private::push_rarrow(&mut _s);
                            ::quote::__private::push_ident(&mut _s, "usize");
                            ::quote::__private::push_group(&mut _s,
                                ::quote::__private::Delimiter::Brace,
                                {
                                    let mut _s = ::quote::__private::TokenStream::new();
                                    ::quote::__private::push_ident(&mut _s, "let");
                                    ::quote::__private::push_ident(&mut _s, "tracker");
                                    ::quote::__private::push_eq(&mut _s);
                                    ::quote::__private::push_colon2(&mut _s);
                                    ::quote::__private::push_ident(&mut _s, "get_size2");
                                    ::quote::__private::push_colon2(&mut _s);
                                    ::quote::__private::push_ident(&mut _s, "default_tracker");
                                    ::quote::__private::push_group(&mut _s,
                                        ::quote::__private::Delimiter::Parenthesis,
                                        ::quote::__private::TokenStream::new());
                                    ::quote::__private::push_semi(&mut _s);
                                    ::quote::__private::push_ident(&mut _s, "let");
                                    ::quote::__private::push_group(&mut _s,
                                        ::quote::__private::Delimiter::Parenthesis,
                                        {
                                            let mut _s = ::quote::__private::TokenStream::new();
                                            ::quote::__private::push_ident(&mut _s, "total");
                                            ::quote::__private::push_comma(&mut _s);
                                            ::quote::__private::push_underscore(&mut _s);
                                            _s
                                        });
                                    ::quote::__private::push_eq(&mut _s);
                                    ::quote::__private::push_colon2(&mut _s);
                                    ::quote::__private::push_ident(&mut _s, "get_size2");
                                    ::quote::__private::push_colon2(&mut _s);
                                    ::quote::__private::push_ident(&mut _s, "GetSize");
                                    ::quote::__private::push_colon2(&mut _s);
                                    ::quote::__private::push_ident(&mut _s,
                                        "get_heap_size_with_tracker");
                                    ::quote::__private::push_group(&mut _s,
                                        ::quote::__private::Delimiter::Parenthesis,
                                        {
                                            let mut _s = ::quote::__private::TokenStream::new();
                                            ::quote::__private::push_ident(&mut _s, "self");
                                            ::quote::__private::push_comma(&mut _s);
                                            ::quote::__private::push_ident(&mut _s, "tracker");
                                            _s
                                        });
                                    ::quote::__private::push_semi(&mut _s);
                                    ::quote::__private::push_ident(&mut _s, "total");
                                    _s
                                });
                            ::quote::__private::push_ident(&mut _s, "fn");
                            ::quote::__private::push_ident(&mut _s,
                                "get_heap_size_with_tracker");
                            ::quote::__private::push_lt(&mut _s);
                            ::quote::__private::push_ident(&mut _s, "TRACKER");
                            ::quote::__private::push_colon(&mut _s);
                            ::quote::__private::push_colon2(&mut _s);
                            ::quote::__private::push_ident(&mut _s, "get_size2");
                            ::quote::__private::push_colon2(&mut _s);
                            ::quote::__private::push_ident(&mut _s, "GetSizeTracker");
                            ::quote::__private::push_gt(&mut _s);
                            ::quote::__private::push_group(&mut _s,
                                ::quote::__private::Delimiter::Parenthesis,
                                {
                                    let mut _s = ::quote::__private::TokenStream::new();
                                    ::quote::__private::push_and(&mut _s);
                                    ::quote::__private::push_ident(&mut _s, "self");
                                    ::quote::__private::push_comma(&mut _s);
                                    ::quote::__private::push_ident(&mut _s, "tracker");
                                    ::quote::__private::push_colon(&mut _s);
                                    ::quote::__private::push_ident(&mut _s, "TRACKER");
                                    ::quote::__private::push_comma(&mut _s);
                                    _s
                                });
                            ::quote::__private::push_rarrow(&mut _s);
                            ::quote::__private::push_group(&mut _s,
                                ::quote::__private::Delimiter::Parenthesis,
                                {
                                    let mut _s = ::quote::__private::TokenStream::new();
                                    ::quote::__private::push_ident(&mut _s, "usize");
                                    ::quote::__private::push_comma(&mut _s);
                                    ::quote::__private::push_ident(&mut _s, "TRACKER");
                                    _s
                                });
                            ::quote::__private::push_group(&mut _s,
                                ::quote::__private::Delimiter::Brace,
                                {
                                    let mut _s = ::quote::__private::TokenStream::new();
                                    ::quote::__private::push_ident(&mut _s, "match");
                                    ::quote::__private::push_ident(&mut _s, "self");
                                    ::quote::__private::push_group(&mut _s,
                                        ::quote::__private::Delimiter::Brace,
                                        {
                                            let mut _s = ::quote::__private::TokenStream::new();
                                            {
                                                use ::quote::__private::ext::*;
                                                let has_iter = ::quote::__private::HasIterator::<false>;
                                                #[allow(unused_mut)]
                                                let (mut cmds, i) = cmds.quote_into_iter();
                                                let has_iter = has_iter | i;
                                                <_ as
                                                        ::quote::__private::CheckHasIterator<true>>::check(has_iter);
                                                while true {
                                                    let cmds =
                                                        match cmds.next() {
                                                            Some(_x) => ::quote::__private::RepInterp(_x),
                                                            None => break,
                                                        };
                                                    ::quote::ToTokens::to_tokens(&cmds, &mut _s);
                                                }
                                            }
                                            _s
                                        });
                                    _s
                                });
                            _s
                        });
                    _s
                };
            Ok(generated.into())
        }
        syn::Data::Union(_data_union) =>
            Err(syn::Error::new_spanned(name,
                    "Deriving GetSize for unions is currently not supported.")),
        syn::Data::Struct(data_struct) => {
            if data_struct.fields.is_empty() {
                let generated =
                    {
                        let mut _s = ::quote::__private::TokenStream::new();
                        ::quote::__private::push_ident(&mut _s, "impl");
                        ::quote::__private::push_colon2(&mut _s);
                        ::quote::__private::push_ident(&mut _s, "get_size2");
                        ::quote::__private::push_colon2(&mut _s);
                        ::quote::__private::push_ident(&mut _s, "GetSize");
                        ::quote::__private::push_ident(&mut _s, "for");
                        ::quote::ToTokens::to_tokens(&name, &mut _s);
                        ::quote::__private::push_group(&mut _s,
                            ::quote::__private::Delimiter::Brace,
                            ::quote::__private::TokenStream::new());
                        _s
                    };
                return Ok(generated.into());
            }
            let mut cmds = Vec::with_capacity(data_struct.fields.len());
            let mut unidentified_fields_count = 0;
            for field in &data_struct.fields {
                let attr =
                    StructFieldAttribute::from_attributes(&field.attrs).map_err(|err|
                                syn::Error::new_spanned(field, err.to_string()))?;
                let accessor =
                    field.ident.as_ref().map_or_else(||
                            {
                                let index = syn::Index::from(unidentified_fields_count);
                                unidentified_fields_count += 1;
                                {
                                    let mut _s = ::quote::__private::TokenStream::new();
                                    ::quote::ToTokens::to_tokens(&index, &mut _s);
                                    _s
                                }
                            },
                        |ident|
                            {
                                let mut _s = ::quote::__private::TokenStream::new();
                                ::quote::ToTokens::to_tokens(&ident, &mut _s);
                                _s
                            });
                if let Some(size) = attr.size {
                    cmds.push({
                            let mut _s = ::quote::__private::TokenStream::new();
                            ::quote::__private::push_ident(&mut _s, "total");
                            ::quote::__private::push_add_eq(&mut _s);
                            ::quote::ToTokens::to_tokens(&size, &mut _s);
                            ::quote::__private::push_semi(&mut _s);
                            _s
                        });
                    continue;
                } else if let Some(size_fn) = attr.size_fn {
                    cmds.push({
                            let mut _s = ::quote::__private::TokenStream::new();
                            ::quote::__private::push_ident(&mut _s, "total");
                            ::quote::__private::push_add_eq(&mut _s);
                            ::quote::ToTokens::to_tokens(&size_fn, &mut _s);
                            ::quote::__private::push_group(&mut _s,
                                ::quote::__private::Delimiter::Parenthesis,
                                {
                                    let mut _s = ::quote::__private::TokenStream::new();
                                    ::quote::__private::push_and(&mut _s);
                                    ::quote::__private::push_ident(&mut _s, "self");
                                    ::quote::__private::push_dot(&mut _s);
                                    ::quote::ToTokens::to_tokens(&accessor, &mut _s);
                                    _s
                                });
                            ::quote::__private::push_semi(&mut _s);
                            _s
                        });
                    continue;
                } else if attr.ignore { continue; }
                cmds.push({
                        let mut _s = ::quote::__private::TokenStream::new();
                        ::quote::__private::push_ident(&mut _s, "let");
                        ::quote::__private::push_group(&mut _s,
                            ::quote::__private::Delimiter::Parenthesis,
                            {
                                let mut _s = ::quote::__private::TokenStream::new();
                                ::quote::__private::push_ident(&mut _s, "total_add");
                                ::quote::__private::push_comma(&mut _s);
                                ::quote::__private::push_ident(&mut _s, "tracker");
                                _s
                            });
                        ::quote::__private::push_eq(&mut _s);
                        ::quote::__private::push_colon2(&mut _s);
                        ::quote::__private::push_ident(&mut _s, "get_size2");
                        ::quote::__private::push_colon2(&mut _s);
                        ::quote::__private::push_ident(&mut _s, "GetSize");
                        ::quote::__private::push_colon2(&mut _s);
                        ::quote::__private::push_ident(&mut _s,
                            "get_heap_size_with_tracker");
                        ::quote::__private::push_group(&mut _s,
                            ::quote::__private::Delimiter::Parenthesis,
                            {
                                let mut _s = ::quote::__private::TokenStream::new();
                                ::quote::__private::push_and(&mut _s);
                                ::quote::__private::push_ident(&mut _s, "self");
                                ::quote::__private::push_dot(&mut _s);
                                ::quote::ToTokens::to_tokens(&accessor, &mut _s);
                                ::quote::__private::push_comma(&mut _s);
                                ::quote::__private::push_ident(&mut _s, "tracker");
                                _s
                            });
                        ::quote::__private::push_semi(&mut _s);
                        ::quote::__private::push_ident(&mut _s, "total");
                        ::quote::__private::push_add_eq(&mut _s);
                        ::quote::__private::push_ident(&mut _s, "total_add");
                        ::quote::__private::push_semi(&mut _s);
                        _s
                    });
            }
            let generated =
                {
                    let mut _s = ::quote::__private::TokenStream::new();
                    ::quote::__private::push_ident(&mut _s, "impl");
                    ::quote::ToTokens::to_tokens(&impl_generics, &mut _s);
                    ::quote::__private::push_colon2(&mut _s);
                    ::quote::__private::push_ident(&mut _s, "get_size2");
                    ::quote::__private::push_colon2(&mut _s);
                    ::quote::__private::push_ident(&mut _s, "GetSize");
                    ::quote::__private::push_ident(&mut _s, "for");
                    ::quote::ToTokens::to_tokens(&name, &mut _s);
                    ::quote::ToTokens::to_tokens(&ty_generics, &mut _s);
                    ::quote::ToTokens::to_tokens(&where_clause, &mut _s);
                    ::quote::__private::push_group(&mut _s,
                        ::quote::__private::Delimiter::Brace,
                        {
                            let mut _s = ::quote::__private::TokenStream::new();
                            ::quote::__private::push_ident(&mut _s, "fn");
                            ::quote::__private::push_ident(&mut _s, "get_heap_size");
                            ::quote::__private::push_group(&mut _s,
                                ::quote::__private::Delimiter::Parenthesis,
                                {
                                    let mut _s = ::quote::__private::TokenStream::new();
                                    ::quote::__private::push_and(&mut _s);
                                    ::quote::__private::push_ident(&mut _s, "self");
                                    _s
                                });
                            ::quote::__private::push_rarrow(&mut _s);
                            ::quote::__private::push_ident(&mut _s, "usize");
                            ::quote::__private::push_group(&mut _s,
                                ::quote::__private::Delimiter::Brace,
                                {
                                    let mut _s = ::quote::__private::TokenStream::new();
                                    ::quote::__private::push_ident(&mut _s, "let");
                                    ::quote::__private::push_ident(&mut _s, "tracker");
                                    ::quote::__private::push_eq(&mut _s);
                                    ::quote::__private::push_colon2(&mut _s);
                                    ::quote::__private::push_ident(&mut _s, "get_size2");
                                    ::quote::__private::push_colon2(&mut _s);
                                    ::quote::__private::push_ident(&mut _s, "default_tracker");
                                    ::quote::__private::push_group(&mut _s,
                                        ::quote::__private::Delimiter::Parenthesis,
                                        ::quote::__private::TokenStream::new());
                                    ::quote::__private::push_semi(&mut _s);
                                    ::quote::__private::push_ident(&mut _s, "let");
                                    ::quote::__private::push_group(&mut _s,
                                        ::quote::__private::Delimiter::Parenthesis,
                                        {
                                            let mut _s = ::quote::__private::TokenStream::new();
                                            ::quote::__private::push_ident(&mut _s, "total");
                                            ::quote::__private::push_comma(&mut _s);
                                            ::quote::__private::push_underscore(&mut _s);
                                            _s
                                        });
                                    ::quote::__private::push_eq(&mut _s);
                                    ::quote::__private::push_colon2(&mut _s);
                                    ::quote::__private::push_ident(&mut _s, "get_size2");
                                    ::quote::__private::push_colon2(&mut _s);
                                    ::quote::__private::push_ident(&mut _s, "GetSize");
                                    ::quote::__private::push_colon2(&mut _s);
                                    ::quote::__private::push_ident(&mut _s,
                                        "get_heap_size_with_tracker");
                                    ::quote::__private::push_group(&mut _s,
                                        ::quote::__private::Delimiter::Parenthesis,
                                        {
                                            let mut _s = ::quote::__private::TokenStream::new();
                                            ::quote::__private::push_ident(&mut _s, "self");
                                            ::quote::__private::push_comma(&mut _s);
                                            ::quote::__private::push_ident(&mut _s, "tracker");
                                            _s
                                        });
                                    ::quote::__private::push_semi(&mut _s);
                                    ::quote::__private::push_ident(&mut _s, "total");
                                    _s
                                });
                            ::quote::__private::push_ident(&mut _s, "fn");
                            ::quote::__private::push_ident(&mut _s,
                                "get_heap_size_with_tracker");
                            ::quote::__private::push_lt(&mut _s);
                            ::quote::__private::push_ident(&mut _s, "TRACKER");
                            ::quote::__private::push_colon(&mut _s);
                            ::quote::__private::push_colon2(&mut _s);
                            ::quote::__private::push_ident(&mut _s, "get_size2");
                            ::quote::__private::push_colon2(&mut _s);
                            ::quote::__private::push_ident(&mut _s, "GetSizeTracker");
                            ::quote::__private::push_gt(&mut _s);
                            ::quote::__private::push_group(&mut _s,
                                ::quote::__private::Delimiter::Parenthesis,
                                {
                                    let mut _s = ::quote::__private::TokenStream::new();
                                    ::quote::__private::push_and(&mut _s);
                                    ::quote::__private::push_ident(&mut _s, "self");
                                    ::quote::__private::push_comma(&mut _s);
                                    ::quote::__private::push_ident(&mut _s, "tracker");
                                    ::quote::__private::push_colon(&mut _s);
                                    ::quote::__private::push_ident(&mut _s, "TRACKER");
                                    ::quote::__private::push_comma(&mut _s);
                                    _s
                                });
                            ::quote::__private::push_rarrow(&mut _s);
                            ::quote::__private::push_group(&mut _s,
                                ::quote::__private::Delimiter::Parenthesis,
                                {
                                    let mut _s = ::quote::__private::TokenStream::new();
                                    ::quote::__private::push_ident(&mut _s, "usize");
                                    ::quote::__private::push_comma(&mut _s);
                                    ::quote::__private::push_ident(&mut _s, "TRACKER");
                                    _s
                                });
                            ::quote::__private::push_group(&mut _s,
                                ::quote::__private::Delimiter::Brace,
                                {
                                    let mut _s = ::quote::__private::TokenStream::new();
                                    ::quote::__private::push_ident(&mut _s, "let");
                                    ::quote::__private::push_ident(&mut _s, "mut");
                                    ::quote::__private::push_ident(&mut _s, "total");
                                    ::quote::__private::push_eq(&mut _s);
                                    ::quote::__private::parse(&mut _s, "0");
                                    ::quote::__private::push_semi(&mut _s);
                                    {
                                        use ::quote::__private::ext::*;
                                        let has_iter = ::quote::__private::HasIterator::<false>;
                                        #[allow(unused_mut)]
                                        let (mut cmds, i) = cmds.quote_into_iter();
                                        let has_iter = has_iter | i;
                                        <_ as
                                                ::quote::__private::CheckHasIterator<true>>::check(has_iter);
                                        while true {
                                            let cmds =
                                                match cmds.next() {
                                                    Some(_x) => ::quote::__private::RepInterp(_x),
                                                    None => break,
                                                };
                                            ::quote::ToTokens::to_tokens(&cmds, &mut _s);
                                        }
                                    }
                                    ::quote::__private::push_semi(&mut _s);
                                    ::quote::__private::push_group(&mut _s,
                                        ::quote::__private::Delimiter::Parenthesis,
                                        {
                                            let mut _s = ::quote::__private::TokenStream::new();
                                            ::quote::__private::push_ident(&mut _s, "total");
                                            ::quote::__private::push_comma(&mut _s);
                                            ::quote::__private::push_ident(&mut _s, "tracker");
                                            _s
                                        });
                                    _s
                                });
                            _s
                        });
                    _s
                };
            Ok(generated.into())
        }
    }
}
const _: () =
    {
        extern crate proc_macro;
        #[rustc_proc_macro_decls]
        #[used]
        #[allow(deprecated)]
        static _DECLS: &[proc_macro::bridge::client::Client] =
            &[proc_macro::bridge::client::Client::expand1(derive_get_size)];
    };
