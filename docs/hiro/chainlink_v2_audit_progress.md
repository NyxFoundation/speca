# Chainlink V2 監査進捗（コンテキスト引き継ぎ用）

## 提出済み (C4に実際に提出)
1. **H-01** — _multiCall selector guard なし (friend提出)
2. **M-03** — Cross-Asset DoS (teoshutuzuumi)
3. **M-01** — Asymmetric price validation checkUpkeep/performUpkeep (teoshutuzuumi)
4. **M-15** — Circuit breaker bounds not validated in fallback (teoshutuzuumi)
5. **M-02** — Shared staleness threshold (提出済み)

## 未提出 (zip済み)
- M-07, M-08, M-14

## 探索済みパターン（全て新規finding なし）
### Round 1: 14 expanded patterns
dutch_auction_rounding, auction_timing_griefing, auction_settlement_reentrancy, fee_on_transfer, token_donation_inflation, oracle_decimal_mismatch, eip1271_reentrancy, order_replay, pause_bypass, performupkeep_manipulation, oracle_staleness_fallback, cowswap_gpv2

### Round 2: 12 attack surfaces
fee-on-transfer, negative oracle price, dutch auction frontrun, checkUpkeep/performUpkeep mismatch, rounding/precision, full balance approval, feeAggregator pull, delete mapping state leak, auction dust griefing, safeTransfer before state update, ERC20 decimal mismatch, EnumerableSet gas DoS

### Round 3: Bulk LLM audit (2000件)
- 104 applicable, 17 high confidence → M-15のみ有効

### Round 4: Deep audit (10 vectors)
isValidSignature, WorkflowRouter, FeeAggregator, _getAssetOutAmount rounding, bid() race condition, performUpkeep batch, invalidateOrders, emergencyWithdraw, token decimals, cross-function state → 全て防御済み

### Round 5: Combination attacks (10 scenarios)
Oracle+bid timing, CowSwap+auction end, multiple auctions, transferForSwap+bid, price staleness+duration, forceApprove+pending order, s_entered scope, donation, checkUpkeep TOCTOU, admin migration → 全て防御済み

### Round 6: 4 fresh sessions (60+ candidates)
CowSwap integration, economic/MEV, access control+state, oracle+external deps → セルフレビューで全て却下

### Round 7: 追加精査
- CowSwap partial fill rounding → CowSwap側のscope
- validTo上限なし → protocol有利方向
- appData未検証 → settlement context外

## 防御パターン（なぜ出にくいか）
1. s_entered global reentrancy guard
2. mulDivUp protocol-favoring rounding
3. whenNotPaused on all critical paths
4. AccessControlDefaultAdminRules
5. forceApprove consistent usage
6. _whenNoLiveAuctions config protection
7. GPv2 domainSeparator + filledAmount replay prevention
8. SafeERC20 consistent usage
9. Constructor-based (non-upgradeable)
10. Oracle decimals normalization

### Round 8: 4 more sessions (compiler, test analysis, CSV, constructor)
- Solidity 0.8.26 compiler bugs → 該当なし
- Constructor parameter edge cases → minBidUsdValue=0/auctionDuration=0 rejected、stalenessThreshold overflow は admin-set で non-issue
- ERC165 compliance → 機能するが explicit ID なし (Info)
- _getAssetOutAmount boundary at elapsedTime==auctionDuration → 正しく endingPriceMultiplier
- validTo 上限なし → Round 7 で既探索、protocol有利
- Test coverage gaps → isValidSignature unit test ゼロ、Caller.sol ゼロだが H-01 でカバー済み
- RoundingFavorsBidder.t.sol PoC 存在 → mulDivUp は protocol-favoring (bidder pays more LINK)

### Round 9: isValidSignature minBidUsdValue bypass 再評価
- test/poc/M05_IsValidSignatureNoMinBid.t.sol で dev team が PoC 作成済み
- bid() は minBidUsdValue ($100) を enforce、isValidSignature() は sellAmount > 0 のみ
- セルフレビュー結果: **QA/Low止まり**
  - Fund loss なし（fair price + mulDivUp protocol-favoring）
  - 経済的に不合理（gas >> dust trade value）
  - minBidUsdValue は efficiency parameter（security mechanism ではない）
  - CowSwap solver は bonded（完全 permissionless ではない）

## 結論
9ラウンド以上の探索で新規 submittable Medium+ finding なし。コードベースは genuinely well-defended。

## 未探索の角度（残り）
- Gas limit attacks on specific functions
- Cross-chain deployment issues (if deployed on L2)
- Solady/OZ library version-specific bugs（0.8.26 compiler は clean）
