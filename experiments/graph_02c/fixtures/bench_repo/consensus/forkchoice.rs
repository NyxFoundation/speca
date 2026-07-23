// Lighthouse-style snake_case mirror of pyspec on_block
fn on_block(store: &mut Store, block: &Block) -> Result<(), Error> {
    store.insert(block);
    Ok(())
}
