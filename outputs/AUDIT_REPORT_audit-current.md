# Security Audit Report: NyxFoundation/audit-current

**Target:** NyxFoundation/audit-current (Sui Move Lending Protocol)
**Commit:** `8a1602713ea9a44f4bddc0070601df15800477aa`
**Date:** 2026-03-09
**Auditor:** SPECA Security Agent

---

## Executive Summary

Sui Move上に構築されたレンディングプロトコルの包括的セキュリティ監査を実施した。対象は math ライブラリ、protocol コントラクト（エントリーポイント + 内部ロジック）、x_oracle の全ソースファイル。

**発見数:** Critical 2件、High 8件、Medium 10件、Low 6件

---

## Critical Findings

### C-01: Flash Loan が Cash Reserve 資金にアクセス可能

| 項目 | 詳細 |
|------|------|
| **重大度** | Critical |
| **場所** | `protocol/sources/internal/market/reserve.move` (borrow_flash_loan / flash_loan_withdraw) |
| **カテゴリ** | Access Control / Fund Safety |

**説明:**
`borrow_flash_loan` は `amount < self.cash` のみをチェックするが、`self.cash` にはプロトコルの `cash_reserve`（プロトコル収益として保護されるべき資金）が含まれている。`flash_loan_withdraw` は `self.cash` を更新せず、`cash - cash_reserve` を上限としたチェックも行わない。

**影響:**
Flash loan により、プロトコル準備金を一時的に引き出すことが可能。手数料計算のバグと組み合わせると、恒久的な準備金損失につながる可能性がある。

**推奨:**
`borrow_flash_loan` のチェックを `amount < self.cash - self.cash_reserve.ceil()` に変更する。

---

### C-02: `repay_fee_rate` が `reserve_factor` として誤用されている

| 項目 | 詳細 |
|------|------|
| **重大度** | Critical |
| **場所** | `protocol/sources/internal/market/market.move` L1025, `reserve.move` L143 |
| **カテゴリ** | Logic Error / Economic |

**説明:**
`market.move` の `accrue_interest` 関数で:
```move
reserve.accrue_interest(asset.repay_fee_rate(), interest_rate, now);
```
`repay_fee_rate`（返済手数料率）が `reserve_factor`（利息のうちプロトコルが受け取る割合）として渡されている。これは意味的に異なるパラメータである。さらに、実際の返済フローでは `repay_fee_rate` は一切適用されておらず、借り手は返済手数料を支払っていない。

**影響:**
1. 利息のプロトコル取り分が `repay_fee_rate` の値に基づいて計算される（本来は `reserve_factor` であるべき）
2. 返済手数料が徴収されない → プロトコル収益損失

**推奨:**
`AssetConfig` に独立した `reserve_factor` フィールドを追加し、`accrue_interest` に正しい値を渡す。返済フローに `repay_fee_rate` の適用ロジックを実装する。

---

## High Findings

### H-01: 清算収益が `ctx.sender()` に送信される

| 項目 | 詳細 |
|------|------|
| **重大度** | High |
| **場所** | `protocol/sources/entry_points/lending/liquidate.move` L159-160, L254-255, L303-304 |
| **カテゴリ** | Access Control |

**説明:**
全清算関数で、押収された担保と返金が `ctx.sender()` に送信される。`PackageCallerCap` は呼び出しを制限するが、収益の受取人は制限しない。コンポーザブルな PTB で、攻撃者が承認済みパッケージ経由で清算を実行すると、収益が攻撃者に渡る。

**推奨:**
清算収益の受取人を `PackageCallerCap` の所有者または明示的に指定されたアドレスに限定する。

---

### H-02: Pyth confidence チェックで u64 オーバーフロー

| 項目 | 詳細 |
|------|------|
| **重大度** | High |
| **場所** | `x_oracle/sources/internal/pyth_adaptor.move` L92-95 |
| **カテゴリ** | Arithmetic Overflow |

**説明:**
```move
let price_conf_diff = (price_conf * CONF_TOLERANCE_DENOMINATOR * 100 as u128) / (price_value as u128);
```
`price_conf * 10000 * 100` は `u64` として計算された後に `u128` にキャストされる。`price_conf > u64::MAX / 1_000_000` (約 1.8e13) の場合、u64 オーバーフローが発生する。

**推奨:**
キャストを先に行う: `((price_conf as u128) * (CONF_TOLERANCE_DENOMINATOR as u128) * 100) / (price_value as u128)`

---

### H-03: `register_pyth_feed` がタイムロックなしでオラクルフィードを置換

| 項目 | 詳細 |
|------|------|
| **重大度** | High |
| **場所** | `x_oracle/sources/entry_points/admin.move` |
| **カテゴリ** | Admin Key Risk / Oracle Manipulation |

**説明:**
AdminCap 保持者は、任意の資産の Pyth フィードを即座に置換可能。タイムロック、マルチシグ要件、古いフィード ID のイベント発行がない。

**影響:**
AdminCap 侵害 → 即座の価格操作 → 大量清算または借入ドレイン。

**推奨:**
オラクルフィード変更にタイムロック（最低24時間）を導入する。

---

### H-04: 清算で Spot 価格、安全性チェックで EMA 価格を使用（非対称）

| 項目 | 詳細 |
|------|------|
| **重大度** | High |
| **場所** | `protocol/sources/internal/market/market.move` L1045-1046 |
| **カテゴリ** | Price Manipulation |

**説明:**
`liquidate_calculate_seize_ctokens` は `get_spot_price`（スポット価格）を使用し、`is_obligation_safe` は `get_price_with_check`（EMA 価格）を使用する。EMA で安全と判断されたポジションが、スポット価格の一時的な変動で清算される可能性がある。

**推奨:**
清算計算と安全性チェックで同一の価格ソースを使用する。

---

### H-05: Math ライブラリ — 除算ゼロのガードなし

| 項目 | 詳細 |
|------|------|
| **重大度** | High |
| **場所** | `math/sources/float.move` — `from_quotient`, `int_div`, `div` |
| **カテゴリ** | DoS / Arithmetic |

**説明:**
3つの関数で除数がゼロの場合のガードがない。レンディングプロトコルでは、交換レート、担保比率、利率がすべて `Decimal` で表現される。初期化されていないマーケット、ゼロ価格のオラクル応答、預金ゼロのリザーブがある場合、トランザクションが中断する。

**推奨:**
各関数にゼロ除数チェックと専用エラーコードを追加する。

---

### H-06: `float::sub` — アンダーフローガードなし

| 項目 | 詳細 |
|------|------|
| **重大度** | High |
| **場所** | `math/sources/float.move` L44 |
| **カテゴリ** | DoS / Arithmetic |

**説明:**
`sub(a, b)` で `b > a` の場合、Move の unsigned integer アンダーフローでランタイムアボートが発生する。`saturating_sub` が別途存在するが、呼び出し側が誤って `sub` を使用するリスクがある。

**推奨:**
`sub` にアサーション `a.value >= b.value` を追加し、明確なエラーコードを返す。

---

### H-07: E-Mode `update_asset_borrow` が `saturating_sub` で借入追跡を暗黙的にゼロ化

| 項目 | 詳細 |
|------|------|
| **重大度** | High |
| **場所** | `protocol/sources/internal/market/emode.move` L188 |
| **カテゴリ** | Accounting / Borrow Cap Bypass |

**説明:**
`old_borrow > new_borrow + current` の場合、`saturating_sub` によりグループ借入追跡がゼロになり、E-Mode 借入キャップがバイパスされる。

**推奨:**
`saturating_sub` の代わりにアサーションを使用し、会計の不整合を検出する。

---

### H-08: グローバル借入キャップが資金移転「後」にチェックされる

| 項目 | 詳細 |
|------|------|
| **重大度** | High |
| **場所** | `protocol/sources/internal/market/market.move` L440 |
| **カテゴリ** | Logic Order |

**説明:**
`handle_borrow` で `max_borrow_amount` チェックが `reserve.borrow_amount` 呼び出しの後に実行される。Move のアトミックなトランザクション特性により実際の資金損失はないが、設計上はプレコンディションチェックであるべき。

**推奨:**
借入キャップチェックを資金移転の前に移動する。

---

## Medium Findings

### M-01: Oracle staleness ウィンドウの不整合

| 項目 | 詳細 |
|------|------|
| **場所** | `pyth_adaptor.move` (30秒) vs `user.move` (`price_delay_tolerance_ms`, デフォルト5秒) |

Pyth の30秒フレッシュネスチェックは `refresh_usd_price` 呼び出し時のみ適用。XOracle の staleness チェックは最後の refresh からの時間を測定し、Pyth 出版からの実際の経過時間は測定しない。

### M-02: EMA/Spot 乖離チェックの分母非対称性

| 項目 | 詳細 |
|------|------|
| **場所** | `x_oracle/sources/entry_points/user.move` L50-56 |

乖離率の分母にスポット価格を使用。スポット上昇時は乖離が小さく見え、下落時は大きく見える非対称性がある。

### M-03: Flash Loan の `emode_group` が呼び出し元制御

| 項目 | 詳細 |
|------|------|
| **場所** | `protocol/sources/entry_points/lending/flash_loan.move` L52 |

呼び出し元が `emode_group` を指定でき、最低手数料率のグループを選択可能。

### M-04: `int_mul` が常にフロア丸め（プロトコルに不利）

| 項目 | 詳細 |
|------|------|
| **場所** | `math/sources/float.move` L63 |

利息や手数料の計算でフロア丸めが使用され、プロトコルが一貫して少なく受け取る。

### M-05: Rate Limiter の `reduce_outflow` が現在のセグメントのみ減少

| 項目 | 詳細 |
|------|------|
| **場所** | `protocol/sources/internal/market/limiter.move` L100-119 |

預金による outflow 減少が現在のセグメントのみに適用。異なるセグメントにまたがる入出金でリミッター値が人工的に膨張する。

### M-06: Limiter の `count_current_outflow` で `timestamp_index < len` 時に全セグメント合計

| 項目 | 詳細 |
|------|------|
| **場所** | `protocol/sources/internal/market/limiter.move` L163-165 |

初期サイクルで `len > timestamp_index` の場合、条件が全セグメントを含む。初期値ゼロのため無害だが、構造的に不正。

### M-07: ADL パラメータ検証なし

| 項目 | 詳細 |
|------|------|
| **場所** | `protocol/sources/internal/market/adl.move` |

`close_factor > 1` や `liquidation_incentive` 上限なしが許容される。

### M-08: 利率モデルのパラメータ検証なし

| 項目 | 詳細 |
|------|------|
| **場所** | `protocol/sources/internal/market/interest.move` |

`base_rate > mid_kink_rate` などの不正な設定で `float::sub` がパニックする。

### M-09: Referral の self-use が Flash Loan 経路で可能

| 項目 | 詳細 |
|------|------|
| **場所** | `protocol/sources/internal/referral.move` (`track_flash_loan_usage`) |

`who != referral code owner` のチェックがなく、自身のリファラルコードで Flash Loan 手数料割引を受けられる。

### M-10: `max_borrow_amount` をゼロに設定可能

| 項目 | 詳細 |
|------|------|
| **場所** | `protocol/sources/entry_points/admin/asset.move` L79-82 |

`max_borrow_amount >= min_borrow_amount` のバリデーションがない。

---

## Low Findings

| ID | 場所 | 説明 |
|----|------|------|
| L-01 | `flash_loan.move` L161-168 | Referral qualification が Flash Loan 元本額で加算（手数料ではなく） |
| L-02 | `admin/decimal.move` L17 | コメントが「Anyone can add」だが AdminCap 必要 |
| L-03 | `admin/whitelist.move` L27-40 | `burn_whitelist` に AdminCap 不要 — 保持者が自己破棄可能 |
| L-04 | `referral.move` L39-51 | `claim_referral_rebates` がサーキットブレーカーを無視 |
| L-05 | `pyth_adaptor.move` L73-75 | `normalize_decimals` で精度 > 9 の場合に暗黙の切り捨て |
| L-06 | `u128.move` L10 | `OVER_FLOW = 1` が他モジュールのエラーコードと衝突 |

---

## Architecture Notes

- **Move の線形型システム**により、従来の EVM ベースプロトコルで見られる reentrancy 攻撃は構造的に防止されている
- **Hot Potato パターン**による Flash Loan は、ローンの返済を同一トランザクション内で強制する
- **ObjectTable による Obligation 管理**は共有オブジェクトとして適切に設計されている
- **PackageCallerCap によるアクセス制御**は、清算や Flash Loan などの高リスク操作に対して適切だが、収益受取人の制御が不足（H-01）

---

## Recommendations Summary

1. **即時対応（Critical）:** Flash Loan の cash reserve アクセス制限、`repay_fee_rate` / `reserve_factor` の分離
2. **高優先度（High）:** 清算収益の受取人制御、Pyth confidence オーバーフロー修正、Oracle フィード変更のタイムロック導入、Math ライブラリのゼロ除算ガード追加
3. **中優先度（Medium）:** Oracle staleness 整合性、丸め方向の統一、パラメータ検証の追加
4. **低優先度（Low）:** ドキュメント整合性、エラーコード標準化
