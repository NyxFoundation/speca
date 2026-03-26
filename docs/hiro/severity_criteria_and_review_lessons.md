# Severity判定基準 & ヒューマンレビュー指摘集

> Chainlink Payment Abstraction V2 (Code4rena 2026-03) の全Finding レビューから抽出した判断基準・教訓。
> 今後のSPECA Finding評価に適用すること。

---

## 1. Severity判定基準（レビュー反映版）

| レベル | 定義 | 条件 |
|--------|------|------|
| **Medium-High** | permissionless + system-wide DoS + recovery困難 | 1つの外部条件で全機能停止。admin recovery pathも詰まる |
| **Medium** | permissionless + 機能DoS（部分的） | 特定機能が停止するが、system-wide ではない |
| **Low-Medium** | 外部条件依存 + recovery pathなし | コード上成立するが、発生条件が外生要因に依存 |
| **Low** | コード上成立 + trusted path依存 | バグとして成立するが、trusted role/admin action が前提 |
| **QA** | self-protection存在 or trusted role or 非経済的 | ユーザーが自己防衛可能、または攻撃コスト > 利益 |
| **Info** | 実害立証なし | コード上の気付きだが、exploitable impactが証明できない |

---

## 2. 判定の核心原則

### 2.1 Permissionless かどうかが最重要

**レビューで一貫して最も重視された軸。** Trusted role が前提の finding は原則 Low 以下。

- ✅ **M-03 (Medium-High)**: `bid()` 経由で permissionless に triggerable。1つの feed revert で全アセット停止
- ❌ **M-04 (QA)**: `AUCTION_WORKER_ROLE` 前提。trusted role のため OOS
- ❌ **M-07 (Low)**: `PRICE_ADMIN_ROLE` + verifier済み report。trusted path 依存
- ❌ **H-01 (High)**: `AUCTION_BIDDER_ROLE` 前提だが、operational role（solver bot）で trust boundary bypass があるため High

**教訓**: 「誰が trigger できるか」を最初に確認。permissionless でなければ Medium は難しい。

### 2.2 Self-protection が存在するか

ユーザーや標準経路が自己防衛できる場合、vulnerability ではなく UX/design issue。

- ❌ **M-06 (QA)**: `bid()` に slippage protection がないが、標準経路の `AuctionBidder` は `getAssetOutAmount()` で exact approve。EOA直接利用は非標準パス
- **指摘原文**: 「exact allowance や wrapper contract で十分 self-protect できます。max approve を前提にした unsafe path がプロトコル標準というわけではありません」

**教訓**: 「プロトコル標準の利用パスで問題が起きるか」を確認。非標準パスの問題は QA。

### 2.3 Impact を盛りすぎない

**最も頻繁に指摘された問題。** 複数の Finding で「impact の書き方が強すぎる」と指摘。

| Finding | 盛りすぎた表現 | 適切な表現 |
|---------|--------------|-----------|
| **M-08** | 「permanent auction freeze」「only fix: deploy new contract」 | 「stuck state + no force-clear + config lockout」。handcrafted performData で他アセット運用は可能 |
| **M-10** | 「sustained DoS via token donation」 | 「config mismatch / onboarding時の運用不整合」。worker が手動 workaround 可能 |
| **M-11** | 「sustained DoS on auction lifecycle」 | 「M-01/M-03 の波及効果の補足」。独立 finding として弱い |
| **M-14** | 「token theft from AuctionBidder」 | 「approval hygiene の best practice 指摘」。residual ≈ 0、admin trust 依存 |

**指摘原文（M-08）**: 「`performUpkeep()` は worker が渡す `performData` に依存しているため、問題の asset を `endedAuctions` から外した handcrafted な `performData` を使えば、他の asset の運用を継続する余地があります」

**教訓**: recovery path が存在するなら「永久停止」「再デプロイのみ」とは書かない。「〜まではコード上成立するが、〜までは言い切れない」という narrow scope で記述。

### 2.4 既存 Finding の言い換えは独立 Finding にならない

- ❌ **M-11 (Info)**: `performUpkeep` の atomic batching 問題 → M-01/M-03 の feed failure の波及効果を batching 観点で言い換えただけ
- **指摘原文**: 「これは新しい exploit primitive というより、既に指摘されている price/feed failure 系の問題（M-01 / M-03）による影響範囲を、atomic batching の観点から言い換えたものに近い」

**教訓**: 根本原因が同じなら独立 finding にしない。「同じ root cause の別 manifestation」として補足に留める。

### 2.5 Prior Art の trust model を確認

- ❌ **M-14**: 引用した先例（TraderJoe #222, Fractional #468, ArtGobblers #238）は **permissionless user の approval** が残る問題。M-14 は **admin-controlled contract 間** の approval — trust model が根本的に違う
- **自己レビューで気付いた**: 「Prior Audit Precedent があるから Medium」は通らない。先例と trust model/前提条件が一致するか確認必須

**教訓**: prior art を引用するとき、attack surface の前提条件（permissionless vs trusted）が一致するか確認。

### 2.6 Defense-in-depth は Low 止まり

Trusted path に対する「defense-in-depth 不足」は valid な指摘だが、severity は Low。

- **M-07 (Low)**: future timestamp 問題。コード上成立するが `PRICE_ADMIN_ROLE` + verifier 済み。defense-in-depth 不足
- **指摘原文**: 「一般 attacker が自由に注入できるバグではなく、oracle/report path に対する defense-in-depth 不足としてみるのが自然です」

**教訓**: 「trusted path だけどチェックがない」= defense-in-depth = Low。Medium にするには permissionless exploitation path が必要。

---

## 3. レポート品質チェックリスト

レビューで指摘された問題から抽出した、提出前チェックリスト:

### 必須チェック

- [ ] **Permissionless trigger か？** — trusted role 前提なら Low 以下
- [ ] **標準利用パスで問題が起きるか？** — 非標準パスなら QA
- [ ] **Impact 表現は narrow scope か？** — 「永久停止」「再デプロイのみ」は recovery path の有無を確認してから
- [ ] **既存 Finding の言い換えになっていないか？** — root cause が同じなら独立 finding にしない
- [ ] **Prior art の trust model は一致するか？** — permissionless vs trusted を確認
- [ ] **Severity across artifacts は統一されているか？** — issue, submission, PR 全てで一致

### PoC チェック

- [ ] Forge test で実際に実行可能（pseudocode 不可）
- [ ] `assertEq` / `assertGt` で impact を検証
- [ ] Attack flow が明確（誰が、何を、どの順で実行するか）

### Impact 表現

- [ ] 「〜まではコード上成立する」「〜までは言い切れない」の境界を明示
- [ ] Recovery path の有無を記載（handcrafted performData, manual workaround 等）
- [ ] Fund loss の exact scope を記載（「全トークン」ではなく「approve したトークンのみ」等）

---

## 4. コードベース防御パターン（なぜ High が出にくかったか）

Chainlink V2 がほとんどの standard attack vector を潰していた理由:

1. **`s_entered` reentrancy guard** — `bid()` と `isValidSignature()` の両方をガード
2. **`assetOutAmount` をcallback前に確定** — callback 中の価格操作不可
3. **`safeTransferFrom` で atomic 支払い強制** — 中途半端な状態が起きない
4. **SafeERC20 一貫使用** — return value 問題なし
5. **`AccessControlDefaultAdminRules`** — admin 権限の安全な移譲
6. **`whenNotPaused` が全 critical path に適用** — emergency stop あり
7. **Constructor-based (non-upgradeable)** — init frontrun / proxy 脆弱性なし
8. **GPv2 `domainSeparator` + `filledAmount`** — EIP-1271 replay 防止
9. **`_whenNoLiveAuctions()` modifier** — ライブ中の設定変更防止
10. **Oracle decimals 正規化** — 両パス（Data Streams / Feed）で実装済み

**教訓**: 堅牢なコードベースでは「permissionless な High/Critical」が構造的に出にくい。trusted role boundary の bypass（H-01）や、外部依存の liveness failure（M-03）が主な attack surface になる。

---

## 5. Finding 別レビューサマリー

### 提出済み・有効

| ID | Severity | 評価 | キーポイント |
|----|----------|------|------------|
| **M-03** | Medium-High | 最有力 | permissionless, cross-asset DoS, deadlock, try-catch 1行で修正 |
| **M-01** | Medium | 有効 | permissionless, oracle staleness で bid/performUpkeep revert |
| **H-01** | High | 有効 | AUCTION_BIDDER_ROLE だが trust boundary bypass が明確 |

### 提出予定・Low

| ID | Severity | 評価 | キーポイント |
|----|----------|------|------------|
| **M-02** | Low | 設計制限 | 単一 stalenessThreshold で dual-oracle 無効化。admin config 依存 |
| **M-07** | Low | 成立するが trusted | future timestamp で stale window 延長。PRICE_ADMIN 依存 |
| **M-14** | Low | 非常に弱い | residual ≈ 0、forceApprove 上書き、admin trust 依存 |

### 却下 (hinin)

| ID | 評価 | 却下理由 |
|----|------|---------|
| **C-01** | duplicate | H-01 と同一 root cause |
| **M-04** | QA | AUCTION_WORKER trusted, fund loss なし |
| **M-05** | QA | 非経済的（ガス代 > 利益） |
| **M-06** | QA | AuctionBidder が self-protect 済み。UX issue |

### 未提出・弱い

| ID | 評価 | 理由 |
|----|------|------|
| **M-08** | Low-Medium | impact 盛りすぎ。narrow scope なら提出可能 |
| **M-09** | Info | 実害立証なし。M-07 の弱い亜種 |
| **M-10** | Low | config mismatch / 運用問題。sustained DoS は言い過ぎ |
| **M-11** | Info | M-01/M-03 の言い換え。独立 finding として弱い |

---

## 6. 次回監査への適用ルール

1. **Finding 生成後、提出前に必ずこの判定基準で self-review する**
2. **Permissionless trigger がない finding は Low 以下でスタート**
3. **Impact 表現は narrow scope で書き、recovery path を明記**
4. **同一 root cause の finding は 1 件にまとめる**
5. **Prior art 引用時は trust model の一致を確認**
6. **PoC は必ず forge test で実行可能な形で提出**
7. **Severity は全 artifacts（issue, submission, PR）で統一**
