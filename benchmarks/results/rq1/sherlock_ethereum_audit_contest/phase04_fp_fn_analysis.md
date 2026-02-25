# Phase 04 偽陽性・偽陰性分析

**対象コンテスト:** Sherlock Ethereum Audit Contest (#1140)
**ベンチマークデータ:** `findings_labels.csv` (102件) + `04_PARTIAL_*.json` (5件)
**生成日:** 2026-02-25

---

## 1. Phase 04 レビュー結果サマリ

Phase 04 は **5件のみ** をレビュー（全て `ethereum/c-kzg-4844` リポジトリ）。

| Finding ID | Phase 04 判定 | 重要度 | Ground Truth | 正否 |
|---|---|---|---|---|
| PROP-57888860-inv-053 | CONFIRMED_VULNERABILITY | Critical | fp_invalid (#282) | **偽陽性** |
| PROP-6a4369e9-inv-037 | DISPUTED_FP | Informational | unknown | 正解（矛盾なし） |
| PROP-57888860-inv-001 | CONFIRMED_VULNERABILITY | High | tp (#203, high) | **正解** |
| PROP-57888860-post-001 | DISPUTED_FP | Informational | unknown | 正解（矛盾なし） |
| PROP-57888860-inv-003 | CONFIRMED_VULNERABILITY | Medium | fixed | 部分正解（実在バグ、修正済） |

### Phase 04 精度（レビュー済み5件のみ）

- **CONFIRMED_VULNERABILITY**: 3件中 1件が偽陽性 → **精度 66.7%**
- **DISPUTED_FP**: 2件中 0件が偽陰性（ground truth不明のため断定不可）
- **偽陽性率（FPR）**: 1/3 = **33.3%**（CONFIRMED判定のうち）
- **偽陰性率（FNR）**: 0/2 = **0%**（DISPUTED判定のうち、GT=tpのものなし）

---

## 2. 偽陽性の詳細分析

### 2.1 Phase 04 が生んだ偽陽性

**PROP-57888860-inv-053** — Point-at-Infinity in c-kzg-4844
- Phase 04: `CONFIRMED_VULNERABILITY` (Critical) — KZG batch verification が point-at-infinity コミットメントを受理しパリング等式不均衡を引き起こすと判定
- Ground Truth: `fp_invalid` (Sherlock #282 "secp256r1 Point-at-Infinity Consensus Split" — **invalid判定**)
- **原因分析**: Phase 04 はコードレベルの技術的正当性は示したが、contest judging との乖離が発生。コンテスト側では「same report found on Geth/Besu/Nethermind」として重複・スコープ外と判定された可能性

### 2.2 Phase 03 全体の偽陽性

Phase 03 の102件中、ground truth ありの80件について:

| 分類 | 件数 | 精度 |
|---|---|---|
| TP（actionable） | 17 | — |
| TP_INFO（informational） | 23 | — |
| Fixed（修正済） | 5 | — |
| Partially Fixed | 2 | — |
| **FP_INVALID** | **33** | — |
| **全体精度（TP+TP_INFO+Fixed+PFixed / labeled）** | — | **58.8%** |
| **Strict精度（TP only / TP+FP）** | — | **34.0%** |

#### Phase 03 Classification別精度

| Classification | Total | TP系 | FP | 精度 |
|---|---|---|---|---|
| vulnerability | 58 | 33 | 25 | 56.9% |
| potential-vulnerability | 22 | 14 | 8 | 63.6% |

#### FP の多いリポジトリ

| リポジトリ | FP件数 |
|---|---|
| status-im/nimbus-eth2 | 9 |
| sigp/lighthouse | 8 |
| OffchainLabs/prysm | 8 |
| grandinetech/grandine | 4 |

Nimbus では #18 (PeerDAS DataColumnSidecars reconstruction) に対して **7件の重複FP** が発生。同一root causeへの複数プロパティ生成が FP を膨張させている。

---

## 3. 偽陰性の分析

### 3.1 Phase 04 のカバレッジ不足

Phase 04 は102件中 **5件（4.9%）** のみレビュー。以下の **16件の strict TP** がレビューされなかった:

| Finding ID | Repo | Issue # | Severity |
|---|---|---|---|
| PROP-56ad1eb2-inv-018 | sigp/lighthouse | #40 | **high** |
| PROP-5a6a79d5-inv-059 | NethermindEth/nethermind | #210 | **high** |
| PROP-6a4369e9-inv-042 | OffchainLabs/prysm | #190 | **high** |
| PROP-5a6a79d5-inv-036 | alloy-rs/evm | #371 | low |
| PROP-6a4369e9-pre-003 | grandinetech/grandine | #376 | low |
| PROP-6a4369e9-inv-009 | grandinetech/grandine | #308 | low |
| PROP-56ad1eb2-inv-029 | grandinetech/grandine | #319 | low |
| PROP-6a4369e9-inv-050 | sigp/lighthouse | #343 | low |
| PROP-6a4369e9-inv-009 | sigp/lighthouse | #308 | low |
| PROP-56ad1eb2-inv-032 | ChainSafe/lodestar | #381 | low |
| PROP-6a4369e9-inv-047 | status-im/nimbus-eth2 | #15 | medium |
| PROP-6a4369e9-inv-009 | status-im/nimbus-eth2 | #308 | low |
| PROP-6a4369e9-inv-049 | status-im/nimbus-eth2 | #216 | medium |
| PROP-56ad1eb2-inv-032 | OffchainLabs/prysm | #381 | low |
| PROP-6a4369e9-inv-009 | OffchainLabs/prysm | #308 | low |
| PROP-57888860-inv-051 | crate-crypto/rust-eth-kzg | #48 | low |

**High severity 3件を含む16件がレビュー未完了** — Phase 04 の最大の問題はカバレッジ不足。

### 3.2 Recall（検出漏れ）

`evaluation_summary.json` によると:

- コンテスト全 actionable issues: **15件**（high: 5, medium: 2, low: 8）
- Phase 03 が検出: **15件**
- **Recall = 100%**（検出漏れゼロ）
- `missed_issues: []`

**Phase 03 のリコールは完璧** — コンテストの全 actionable issue を検出済み。偽陰性はパイプライン全体では存在しない。

---

## 4. 総合メトリクス

### Pipeline 全体（evaluation_summary.json）

| メトリクス | 値 |
|---|---|
| Recall（全severity） | **100%** (15/15) |
| Recall (high) | 100% (5/5) |
| Recall (medium) | 100% (2/2) |
| Recall (low) | 100% (8/8) |
| Precision (auto) | **65.3%** |
| Precision (conservative) | 31.4% |
| F1 | **0.79** |
| ユニーク TP issues | 13 |
| ユニーク TP_INFO issues | 11 |
| ユニーク FP issues | 20 |

### Phase 04 のみ

| メトリクス | 値 |
|---|---|
| レビュー件数 | 5 / 102 (4.9%) |
| CONFIRMED → TP | 1/3 (33.3%) |
| CONFIRMED → FP | 1/3 (33.3%) |
| CONFIRMED → Fixed | 1/3 (33.3%) |
| DISPUTED → 矛盾なし | 2/2 (100%) |
| 未レビュー strict TP | 16件（high 3件含む） |

---

## 5. 結論と改善提案

### 偽陽性（FP）の課題
1. **Phase 03 の FP率 41.2%**（33/80 labeled findings）は高い。特に Nimbus (#18) と Lighthouse への重複報告が顕著
2. **Phase 04 の FP判別能力**: 5件中1件の FP を見逃し（CONFIRMED判定）。サンプル少数のため断定不可だが、contest judging 基準との乖離がある
3. **重複 FP の根本原因**: 同一 contest issue に対して複数のプロパティが生成され、それぞれが独立した finding として報告される構造的問題

### 偽陰性（FN）の課題
1. **Phase 03 の Recall は 100%** — パイプラインの検出能力自体は極めて高い
2. **Phase 04 のカバレッジ 4.9%** が最大の課題 — 16件の strict TP（high 3件含む）が未レビュー
3. Phase 04 が全件レビューできれば、FP フィルタリングの有効性を正確に評価可能

### 改善提案
1. **Phase 04 のスケーラビリティ**: バッチサイズ・ワーカー数を増やし全102件をレビュー対象にする
2. **重複検出**: 同一 contest issue に対する複数 finding を事前に集約（dedup）
3. **FP パターン学習**: Nimbus #18 のような「同一 root cause × 複数 validation path」パターンの自動検出
