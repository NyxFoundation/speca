# Security Audit Report: NyxFoundation/audit-current

**Target:** NyxFoundation/audit-current (Current Finance — Sui Move Lending Protocol)
**Commit:** `8a1602713ea9a44f4bddc0070601df15800477aa`
**Date:** 2026-03-09
**Auditor:** SPECA Pipeline (Phase 01a→01b→01e→02c→03→04)
**Spec Source:** README.md (Sherlock Contest #1256 Q&A + invariants)

---

## Executive Summary

SPECAパイプライン全6フェーズを実行。README仕様書から16の関連ドキュメントを発見し、241のセキュリティプロパティを生成、238件をコードに対して証明ベース監査、3-gate FPフィルタで最終レビューを実施。

**Pipeline Raw:** CONFIRMED 22 + POTENTIAL 8 = 30件
**重複排除後:** ユニーク脆弱性 **14件** (High 7 / Medium 7)

---

## High Findings (7件)

### H-01: `repay_fee_rate` が `reserve_factor` として誤用 — プロトコル収益損失 + マーケット凍結リスク

| 項目 | 詳細 |
|------|------|
| **重大度** | High |
| **場所** | `market.move:1025` → `reserve.move:accrue_interest` |
| **関連PROP** | PROP-01b-partial-inv-008, partial3-inv-037, partial2-inv-006, partial-asm-003, partial1-inv-034, partial-inv-021 (6件が同一バグ) |

`accrue_interest` で `asset.repay_fee_rate()` が `reserve_factor` パラメータとして渡される。これにより:
1. **返済手数料が一切徴収されない** — `repay_fee_rate` は利息計算に流用され、返済フローでは適用されない
2. **`cash_reserve` が不正に蓄積** — 本来の reserve_factor (例:10%) ではなく repay_fee_rate (例:0.01%) で計算
3. **`cash_reserve > cash` 到達でマーケット凍結** — `withdraw_underlying` の `cash >= cash_reserve.ceil()` アサーションでリバート

---

### H-02: First Depositor Attack — Exchange Rate Inflation による預金盗取

| 項目 | 詳細 |
|------|------|
| **重大度** | High |
| **場所** | `reserve.move:mint_ctokens` (int_div truncation) |
| **関連PROP** | PROP-01b-partial3-inv-046, partial1-inv-005, partial3-inv-003 (3件が同一バグ) |

最初の預金者が exchange_rate を1以上にインフレさせると、後続の少額預金で `int_div(amount, exchange_rate) == 0` となり 0 cToken が発行される。被害者の資金はリザーブに取り込まれ、攻撃者が唯一の cToken 保持者として回収可能。`mint_amount > 0` のアサーションが欠如。

---

### H-03: 清算時の Spot/EMA 価格非対称 — 過剰担保押収

| 項目 | 詳細 |
|------|------|
| **重大度** | High |
| **場所** | `market.move:liquidate_calculate_seize_ctokens` (L1045-1046 spot) vs `ensure_liquidate_borrow_allowed` (EMA) |
| **関連PROP** | PROP-01b-partial1-inv-038, partial3-inv-015, partial1-post-003 (3件が同一バグ) |

清算適格判定は EMA 価格、押収量計算は Spot 価格を使用。Spot が EMA から乖離した瞬間（担保トークン暴落時等）に、借り手から正当化を超える担保が押収される。`close_factor_bypass` (collateral ≤ 1.01 × debt) 到達後は全担保ドレインも可能。

---

### H-04: 自己清算によるインセンティブ窃取

| 項目 | 詳細 |
|------|------|
| **重大度** | High |
| **場所** | `liquidate.move:liquidate_as_coin` — liquidator != borrower チェックなし |
| **関連PROP** | PROP-01b-partial3-inv-013, partial-inv-025, partial2-inv-027 (3件が同一バグ) |

借り手が自身のポジションを清算し、清算インセンティブ（`D × incentive`）を自身で回収可能。Flash Loan と組み合わせ、1 PTB 内で借入→自己清算→Flash Loan返済が可能。

---

### H-05: `util_rate > 1` によるマーケット凍結 + 利率上限突破

| 項目 | 詳細 |
|------|------|
| **重大度** | High |
| **場所** | `reserve.move:util_rate` (L65-72), `interest.move:calc_interest` |
| **関連PROP** | PROP-01b-partial-inv-026, partial1-inv-021, partial3-inv-019, partial3-inv-038 (4件が同一バグ) |

H-01 の下流影響。`cash_reserve > cash` 到達時に `util_rate = debt / (debt + cash - cash_reserve)` が1を超え、利率モデルが `max_borrow_rate` を超える値を返す。全預金者の引き出しと全借入がリバートし、マーケットが凍結。

**Note:** H-01 と根本原因は同一だが、H-01 が修正されても `reserve_factor` の値が大きすぎる場合に独立して発生し得る。

---

### H-06: 清算で Dust Position 残留 — 回収不能な不良債権

| 項目 | 詳細 |
|------|------|
| **重大度** | High |
| **場所** | `market.move:liquidation_inner` (L691-793) |
| **関連PROP** | PROP-01b-partial-inv-018 |

債務が `min_borrow_amount` と `2 × min_borrow_amount` の間にある obligation を清算すると、`close_factor` (50%) の返済後に残留債務が `min_borrow_amount` を下回る。`enforce_post_borrow_repay_invariant` が清算パスでは呼ばれないため、dust position が恒久的に残留し不良債権化する。

---

### H-07: Borrow Fee 未徴収

| 項目 | 詳細 |
|------|------|
| **重大度** | High |
| **場所** | `borrow.move:borrow` エントリーポイント |
| **関連PROP** | PROP-01b-partial1-inv-033 |

借入エントリーポイントで手数料が一切差し引かれない。プロトコルの借入手数料収益が完全に失われている。

---

## Medium Findings (7件)

### M-01: `deposit_limit_breached` の `cash_reserve` 二重減算 — 預金キャップバイパス

| 項目 | 詳細 |
|------|------|
| **場所** | `reserve.move:deposit_limit_breached` (L87-90) |
| **関連PROP** | PROP-01b-partial-pre-008, partial1-pre-003, partial2-inv-028 (3件が同一バグ) |

`total_deposit_plus_interest` は `exchange_rate × total_supply = cash + debt - cash_reserve` で既に `cash_reserve` を控除済み。チェック式で再度 `- cash_reserve` するため、実効キャップが `max_deposit_amount + cash_reserve` になる。

---

### M-02: Rate Limiter の `reduce_outflow` がセグメント境界で不整合

| 項目 | 詳細 |
|------|------|
| **場所** | `limiter.move:reduce_outflow` |
| **関連PROP** | PROP-01b-partial2-inv-040 |

預金による outflow 減少が現在のセグメントのみに適用される。異なるセグメントで行われた引き出しの outflow は減少しないため、リミッター値が人工的に膨張し、正当な引き出しがブロックされ得る。

---

### M-03: Oracle Staleness の選択的悪用

| 項目 | 詳細 |
|------|------|
| **場所** | `x_oracle/user.move:get_price_with_check` |
| **関連PROP** | PROP-01b-partial1-inv-027 |

攻撃者が PTB 内で担保トークンの `refresh_usd_price` を呼んで新鮮な価格をスタンプし、債務トークンのオラクルは最大 staleness (5秒) のまま借入を実行。債務の過小評価により、担保を超える借入が可能。

---

### M-04: マーケット登録時の Oracle フィード未検証

| 項目 | 詳細 |
|------|------|
| **場所** | `admin/market.move:register_market` |
| **関連PROP** | PROP-01b-partial3-asm-003 |

新マーケット登録時に XOracle のフィード存在チェックがない。管理者がフィードなしで登録すると、ユーザーが預金後に引き出し不能になる（`get_price_with_check` でリバート）。

---

### M-05: ADL 停止条件の floor/ceil 不整合

| 項目 | 詳細 |
|------|------|
| **場所** | `market.move:try_stop_borrow_deleverage` (L686) |
| **関連PROP** | PROP-01b-partial-post-007 |

担保・返済パスでは `.ceil()` を使用するが、清算借入パスでは `.floor()` を使用。`target_amount` と `target_amount+1` の間にある場合、ADL が早期停止する。

---

### M-06: Referral パラメータの合算値未検証

| 項目 | 詳細 |
|------|------|
| **場所** | `referral.move:update_referral_params` |
| **関連PROP** | PROP-01b-partial-inv-034 |

`referrer_bps` と `referee_bps` は個別に `< DENOMINATOR` をチェックするが、合算 `referrer_bps + referee_bps < 10000` は検証しない。管理者が両方に 9000 を設定すると、リファラル割引合計が 180% になる。

---

### M-07: E-Mode `collateral_factor_bps = 0` が許可される

| 項目 | 詳細 |
|------|------|
| **場所** | `admin/emode.move:create_emode_params_inner` (L175) |
| **関連PROP** | PROP-01b-partial1-inv-024 |

`collateral_factor_bps < BPS_DENOMINATOR` のみチェックし `> 0` を検証しない。管理者が 0 を設定すると、該当資産の担保価値がゼロ扱いになり全ポジションが即座に清算可能。

---

## 重複マッピング (30件 → 14件)

| ユニーク ID | 関連PROP (重複) | 件数 |
|------------|-----------------|------|
| H-01 | partial-inv-008, partial3-inv-037, partial2-inv-006, partial-asm-003, partial1-inv-034, partial-inv-021 | 6 |
| H-02 | partial3-inv-046, partial1-inv-005, partial3-inv-003 | 3 |
| H-03 | partial1-inv-038, partial3-inv-015, partial1-post-003 | 3 |
| H-04 | partial3-inv-013, partial-inv-025, partial2-inv-027 | 3 |
| H-05 | partial-inv-026, partial1-inv-021, partial3-inv-019, partial3-inv-038 | 4 |
| H-06 | partial-inv-018 | 1 |
| H-07 | partial1-inv-033 | 1 |
| M-01 | partial-pre-008, partial1-pre-003, partial2-inv-028 | 3 |
| M-02 | partial2-inv-040 | 1 |
| M-03 | partial1-inv-027 | 1 |
| M-04 | partial3-asm-003 | 1 |
| M-05 | partial-post-007 | 1 |
| M-06 | partial-inv-034 | 1 |
| M-07 | partial1-inv-024 | 1 |
| **合計** | | **30 → 14** |

---

## Pipeline Statistics

| Phase | 入力 | 出力 | 所要時間概算 |
|-------|------|------|-------------|
| 01a Spec Discovery | README URL | 16 spec URLs | ~5min |
| 01b Subgraph Extraction | 16 specs | 4 subgraphs + .mmd | ~15min |
| 01e Property Generation | 4 subgraphs | 241 properties | ~10min |
| 02c Code Pre-resolution | 241 props | 238 enriched (3 Informational dropped) | ~15min |
| 03 Audit Map | 238 props | 9 vuln + 21 potential + 207 safe + 1 other | ~60min |
| 04 Review (3-gate FP) | 30 non-safe | 22 CONFIRMED + 8 POTENTIAL | ~10min |
