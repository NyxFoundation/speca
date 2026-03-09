// ============================================================
// PREREQUISITE PATCH: Add to x_oracle::x_oracle module
// ============================================================
//
// File: contracts/x_oracle/sources/internal/x_oracle.move
// Add this function AFTER the existing update_price function
// (around line 205, just before the closing brace).
//
// This #[test_only] helper allows setting spot and EMA prices
// independently, which is needed to demonstrate price
// divergence vulnerabilities in liquidation and safety checks.
// ============================================================

// ---- Paste this into x_oracle.move after update_price<T> ----

// #[test_only]
// public fun update_price_divergent<T>(
//     self: &mut XOracle,
//     clock: &Clock,
//     spot_value: u64,
//     ema_value: u64,
// ) {
//     let coin_type = std::type_name::with_defining_ids<T>();
//     let time = sui::clock::timestamp_ms(clock) / 1000;
//     let ema = x_oracle::price_feed::new_component(ema_value, time);
//     let spot = x_oracle::price_feed::new_component(spot_value, time);
//     update_price_feed(self, usd(), coin_type, spot, ema);
// }

// ---- End of patch ----
