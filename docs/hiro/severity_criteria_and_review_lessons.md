# Severity判定基準 & セルフチェックリスト

> 監査対象: Chainlink Payment Abstraction V2 (Code4rena 2026-03)
> ソース: grandchildrice レビュー + 有識者フィードバック + 9ラウンド探索 + 全イシューコメント + AI agent出力
> **最終更新: 2026-03-27**

---

## 0. 有識者フィルタリング基準（最優先で適用）

### 0.1 Severity 閾値（Sherlock / C4 準拠）

| Severity | 条件 | 金額閾値 |
|----------|------|---------|
| **High** | 直接損失、外部条件なし、permissionless external 関数がエントリーポイント | ユーザーが元本/yieldの >1% AND >$10 を失う |
| **Medium** | 条件付き直接損失（>0.01% AND >$10）、またはコア機能の破壊 | 条件は通常運用で自然に発生しうるもの1つまで |
| **弾く** | リスク管理パラメータの緩みのみ（deposit limit超過等、直接損失なし） | — |
| **弾く** | 1件あたり <$10 の griefing で攻撃コストが上回る場合 | — |
| **弾く** | 業界で既知の design pattern（他プロトコルでも同様の実装がある） | — |

> **重要**: 発生条件が特殊だと**運用ミスとして弾かれがち**。Medium/Low の判定ではまず「攻撃シナリオに管理者権限・onlyOwner・運用上のミスが必須かどうか」でフィルタし、**完全に誰でも実行できる external 関数がエントリーポイントになっているもの**だけに PoC を作る。

### 0.2 Admin操作の現実性フィルタ

| 判定 | パターン |
|------|---------|
| **通過** | デプロイ時の初期パラメータ設定（close_factor, min_borrow_amount, deposit_cap 等） |
| **通過** | ルーティンの運用操作（flash loan有効化、reward pool設定、非担保asset設定等） |
| **弾く** | 緊急措置の同時発動（矛盾した運用状態: ADL + liquidation_pause 等） |
| **弾く** | admin neglect（緊急機能を長時間放置等） |
| **弾く** | admin misconfiguration（名前が紛らわしいだけ、ドキュメントバグ） |
| **弾く** | trusted role の悪用前提（ホワイトリスト契約等） |

### 0.3 前提条件の連鎖深度

前提条件が重なるほど非現実的になる。**2つ以上の稀な条件の同時成立は疑う。**

| 判定 | パターン |
|------|---------|
| **通過** | 前提なし、または通常運用で自然に満たされる条件1つ |
| **弱い** | 外部条件（市場ボラティリティ）+ 特定の内部状態 |
| **弾く** | 別レポートのバグが前提 |
| **弾く** | 複数の稀な条件の同時成立（ADL発動 × 特定emode構成 × mempool監視 等） |

### 0.4 攻撃コスト vs 利益

- **dust position / 過剰担保没収**: 失われる金額の規模と攻撃コストで severity が Info まで落ちる
- **PoC の肝**: **なるべく低コストで高い金額を exploit するシナリオを書く** — これが severity を左右する最大の変数
- **攻撃者が得するがコスト > 利益の場合**: 報告はするが**提出は保留**
- **影響の直接性**: 直接的な fund loss があるか。間接的リスクだけでは不十分
  - High: 直接損失、外部条件なし
  - Medium: 条件付き直接損失
  - 弾く: リスク管理パラメータの緩みのみ（直接損失なし）
  - 弾く: 1件あたり <$10 で攻撃コストが上回る griefing

### 0.5 Design Decision との境界

「バグか意図的設計か」が曖昧な場合:

| 判定 | パターン |
|------|---------|
| バグ寄り | コード内に TODO コメントがある |
| バグ寄り | 業界のベストプラクティスに反する |
| design decision 寄り | 他プロトコルでも同様の実装がある |

### 0.6 チェーン固有の制約

ターゲットチェーンのアーキテクチャで攻撃が成立するか確認:
- **Ethereum L1（Chainlink V2 のターゲット）**: MEV/front-run は成立する。block.timestamp 操作は ~15s
- **L2 (Arbitrum/Optimism)**: sequencer downtime、L1→L2 メッセージ遅延の考慮が必要
- **Sui**: narwhal/bullshark コンセンサスで従来型 mempool front-run が構造的に困難
- **一般**: front-run 前提のシナリオはチェーンアーキテクチャで成立しない可能性を常に確認

### 0.7 PoC 作成規約

- **攻撃が成功したときにテストが PASS するように書く**（revert を期待するのではなく、攻撃者の残高増加等を assert）
- **報告ごとにテストファイルを分ける**（1 finding = 1 .t.sol）
- **C4 フォーマット**: `docs/report_templates/code4rena.md` に準拠
- **完全に動く exploit code** を提出（pseudocode 不可）
- **エントリーポイント**: permissionless な external 関数から開始
- **コーディング規約**: コメントは日本語 OK、変数名・関数名は英語、forge test の naming convention に従う
- **mock test で証明できないことは code walkthrough に切り替え**（M-15 教訓）
- **具体的な数値シナリオはコードで再現可能な場合のみ記載**

### 0.8 HIGH 専用探索戦略

> 有識者: 「Highだけ見つける戦略でいきましょ！一番手っ取り早いのは過去事例をもとに類似バグを探索すること」

1. **過去の監査レポート・バグバウンティレポートを網羅的に CSV 化**
   - `benchmarks/data/defi_audit_reports/code4rena_all_issues.csv` (3.3M行)
   - `benchmarks/data/defi_audit_reports/sherlock_all_issues.csv` (406K行)
   - `benchmarks/data/defi_audit_reports/codehawks_all_issues.csv` (80K行)
2. **HIGH severity のみをフィルタし、attack pattern をキーワードで分類**
3. **監査対象のコードベースに対して pattern matching で類似箇所を検索**
4. **新規発見があったら「発見！」を含むコミットメッセージで push**

---

## 1. Severity判定基準（レビュー反映版）

| レベル | 定義 | 条件 |
|--------|------|------|
| **High** | 直接的 fund loss、permissionless、外部条件なし | external 関数がエントリーポイント。trust boundary bypass + fund loss path。>1% AND >$10 |
| **Medium-High** | permissionless + system-wide DoS + recovery困難 | 1つの外部条件で全機能停止。admin recovery pathも詰まる |
| **Medium** | 条件付き直接損失 or コア機能破壊 | permissionless + 機能DoS（部分的）。>0.01% AND >$10 |
| **Low-Medium** | 外部条件依存 + recovery pathなし | コード上成立するが、発生条件が外生要因に依存 |
| **Low** | コード上成立 + trusted path依存 | trusted role/admin action が前提。defense-in-depth 不足 |
| **QA** | self-protection存在 or trusted role or 非経済的 | 攻撃コスト > 利益、または design decision |
| **Info** | 実害立証なし | exploitable impact が証明できない |

---

## 2. 判定の核心原則

### 2.1 Permissionless かどうかが最重要

**レビューで一貫して最も重視された軸。** Trusted role が前提の finding は原則 Low 以下。

- ✅ **M-03 (Medium-High)**: `bid()` 経由で permissionless に triggerable。1つの feed revert で全アセット停止
- ❌ **M-04 (QA)**: `AUCTION_WORKER_ROLE` 前提。trusted role のため OOS
- ❌ **M-07 (Low)**: `PRICE_ADMIN_ROLE` + verifier済み report。trusted path 依存
- ✅ **H-01 (High)**: `AUCTION_BIDDER_ROLE` 前提だが、operational role（solver bot）で trust boundary bypass があるため High

**教訓**: 「誰が trigger できるか」を最初に確認。permissionless でなければ Medium は難しい。

### 2.2 Self-protection が存在するか

ユーザーや標準経路が自己防衛できる場合、vulnerability ではなく UX/design issue。

- ❌ **M-06 (QA)**: `bid()` に slippage protection がないが、標準経路の `AuctionBidder` は `getAssetOutAmount()` で exact approve。EOA直接利用は非標準パス
- **grandchildrice (#158)**: 「exact allowance や wrapper contract で十分 self-protect できます。max approve を前提にした unsafe path がプロトコル標準というわけではありません」
- ❌ **M-05 (QA)**: `isValidSignature()` に minBidUsdValue チェックがないが、micro-fill でも fair price (mulDivUp)。gas >> profit で経済的に不合理

**教訓**:
- 「プロトコル標準の利用パスで問題が起きるか」を確認。非標準パスの問題は QA
- **efficiency parameter と security mechanism を区別**: minBidUsdValue は gas 効率化のためであり、bypass しても fund loss が発生しない場合は QA

### 2.3 Impact を盛りすぎない

**最も頻繁に指摘された問題。** 複数の Finding で「impact の書き方が強すぎる」と指摘。

| Finding | 盛りすぎた表現 | 適切な表現 |
|---------|--------------|-----------|
| **M-08** | 「permanent auction freeze」「only fix: deploy new contract」 | 「stuck state + no force-clear + config lockout」。handcrafted performData で他アセット運用は可能 |
| **M-10** | 「sustained DoS via token donation」 | 「config mismatch / onboarding時の運用不整合」。worker が手動 workaround 可能 |
| **M-11** | 「sustained DoS on auction lifecycle」 | 「M-01/M-03 の波及効果の補足」。独立 finding として弱い |
| **M-14** | 「token theft from AuctionBidder」 | 「approval hygiene の best practice 指摘」。residual ≈ 0、admin trust 依存 |
| **M-15** | 「5x loss」のテーブル + console2.log PoC | 「degree depends on divergence from minAnswer」+ code walkthrough |

**教訓**:
- recovery path が存在するなら「永久停止」「再デプロイのみ」とは書かない
- 「〜まではコード上成立するが、〜までは言い切れない」という narrow scope で記述
- **具体的な数値シナリオ（5x loss 等）は、コードで証明できない限り書かない**

### 2.4 既存 Finding の言い換えは独立 Finding にならない

- ❌ **M-11 (Info)**: `performUpkeep` の atomic batching 問題 → M-01/M-03 の feed failure の波及効果を batching 観点で言い換えただけ

**教訓**: 根本原因が同じなら独立 finding にしない。「同じ root cause の別 manifestation」として補足に留める。

### 2.5 Prior Art の trust model を確認

- ❌ **M-14**: 引用した先例は **permissionless user** の問題。M-14 は **admin-controlled** — trust model が違う
- ❌ **M-15 circuit breaker**: 先例15件は全て Medium だが、本件は fallback path only + Chainlink 自社 → Low に downgrade

**教訓**: **先例の件数だけで severity を決めない**。trust model が一致するか必ず確認。

### 2.6 Defense-in-depth は Low 止まり

「trusted path だけどチェックがない」= defense-in-depth = **Low**。Medium にするには permissionless exploitation path が必要。

### 2.7 Trust Boundary Violation の framing

trusted role でも **trust hierarchy の逸脱** が明確なら High になりうる。

**grandchildrice (#171)** H-01 7点フィードバック:
1. **Severity統一**: 全 artifacts で severity を統一
2. **Impact正確化**: 「全トークン drain」→「_multiCall 中に approve したトークンのみ」
3. **Trust boundary を明示**: 「AUCTION_BIDDER_ROLE → DEFAULT_ADMIN_ROLE bypass」
4. **2-step exploit の区別**: same root cause でも exploit manifestation が異なるなら独立 finding
5. **PoC**: `_multiCall` が AuctionBidder として実行されることを明記
6. **Actor 記述**: 「Permissionless」ではなく「malicious operator or compromised bidder role」
7. **Mitigation の幅**: selector restriction + allowlist + clear temp approval + context 制限

### 2.8 経済的合理性チェック

攻撃コストが利益を上回る場合は QA。攻撃者が得するがコスト > 利益なら**報告はするが提出は保留**。

### 2.9 2パスの非対称性は自動的に vulnerability ではない

非対称性を見つけたら「この非対称性を exploit して誰が得をするか？」を考える。得をする人がいないなら QA/Info。

---

## 3. 提出前チェックリスト

### Severity チェック

- [ ] **Permissionless trigger か？** — trusted role 前提なら Low 以下
- [ ] **標準利用パスで問題が起きるか？** — 非標準パスなら QA
- [ ] **Impact 表現は narrow scope か？** — recovery path の有無を確認
- [ ] **既存 Finding の言い換えになっていないか？** — root cause が同じなら独立 finding にしない
- [ ] **Prior art の trust model は一致するか？** — permissionless vs trusted を確認
- [ ] **Severity across artifacts は統一されているか？** — issue, submission, PR 全てで一致
- [ ] **経済的に合理的な攻撃か？** — gas cost vs profit を概算比較
- [ ] **Trust boundary violation か、defense-in-depth 不足か？** — 前者は High 候補、後者は Low
- [ ] **前提条件は2つ以上の稀な条件の同時成立を要求していないか？**
- [ ] **Admin操作が前提なら、それは通常運用で起こりうるか？**

### C/C++ OSS Human Review チェック（RQ2a 教訓）

- [ ] **コード存在確認**: 指摘されたファイル・関数・行番号が実在するか grep/find で確認。不在なら即 FP
- [ ] **最新ブランチ確認**: バグが最新で修正済みかチェック。修正済みなら PR 不要
- [ ] **フレームワーク保証**: ライブラリ/フレームワーク固有の安全機構（ImageMagick CoderBlobSupportFlag 等）を確認
- [ ] **関数セマンティクス追跡**: return/goto/longjmp の制御フローを正確に追跡。特にエラーパスの cleanup 順序
- [ ] **メンテナ確認**: ドメイン知識が必要な判定はメンテナに確認。メンテナ reject = FP 確定
- [ ] **他モデル相互参照**: 同じバグが Opus/Sonnet 4/DeepSeek R1 で検出されているか確認。複数モデルで TP なら信頼度高
- [ ] **GT 依存判定の排除**: Ground Truth にないことは FP の理由にならない。コードの実態で判定
- [ ] **スコープ確認**: vendored ヘッダー、テストコード、deprecated wrapper は FP
- [ ] **重複排除**: 同一根本原因の finding が複数あれば統合（N5-npd-014 と npd-015 等）
- [ ] **上流 PR 投稿前の最新確認**: フォークして最新コードで脆弱性が残存するか確認してから PR

### PoC チェック

- [ ] **攻撃成功時にテストが PASS する**（revert 期待ではなく残高増加等を assert）
- [ ] `assertEq` / `assertGt` で impact を検証 — console2.log + コメントは PoC ではない
- [ ] Attack flow が明確（誰が、何を、どの順で実行するか）
- [ ] **Mock test で証明できることだけを assertion で書く**
- [ ] **具体的な数値シナリオはコードで再現可能な場合のみ記載**
- [ ] **完全に動く exploit code**（pseudocode 不可）
- [ ] **permissionless な external 関数から開始**

### Impact 表現

- [ ] 「〜まではコード上成立する」「〜までは言い切れない」の境界を明示
- [ ] Recovery path の有無を記載
- [ ] Fund loss の exact scope を記載（「全トークン」ではなく「approve したトークンのみ」等）
- [ ] **efficiency parameter vs security mechanism を区別**
- [ ] **タイトルが impact を過大表現していないか** — 「Permanent」「Full Drain」「Sustained DoS」は慎重に
- [ ] **Actor の記述が正確か** — 「Permissionless」なのか「malicious operator」なのか

---

## 4. AI Agent 出力のフィルタリング基準

### AI が生成した Finding の典型的な問題パターン

| バイアス | 具体例 | 対処 |
|---------|--------|------|
| **Severity インフレ** | M-08「Permanent Freeze」、M-10「Sustained DoS」 | narrow scope に書き直す。recovery path を必ず確認 |
| **パターンマッチ過信** | M-06を「Revolution Protocol #91と同じ」 | trust model が異なる先例を引用していないか確認 |
| **non-exploitable gap の報告** | M-05「2パスの非対称性」 | 経済的合理性を確認。得をする人がいないなら QA |
| **defense-in-depth を Medium に** | M-07「future timestamp accepted」 | trusted path なら Low |
| **mock PoC で証明不能なことを assertion** | M-15 旧PoC「console2.log で 5x loss」 | mock で再現できないなら code walkthrough に切り替え |
| **「GT外 = FP」バイアス** | DeepSeek R1 が GT にないバグを一律 FP 判定 | GT は参考値。コードを読んでバグの実在を確認すること |
| **Cross-project data contamination** | DeepSeek R1 が全プロジェクトに AuctionBidder.sol を混入 | 対象リポジトリに存在しないファイルへの言及は即 FP |
| **フレームワーク保証の見落とし** | N2-npd-010: ImageMagick CoderBlobSupportFlag 無視 | フレームワーク固有の安全機構を確認してから判定 |
| **C関数セマンティクス誤読** | M2b-mlk-008: do_cache_free() return 後の制御フロー誤解 | 関数の return が呼び出し元に戻ることを追跡 |
| **ドメイン知識不足による投機的判定** | M2b-mlk-003: memcached refcount 不変条件の無視 | メンテナの確認が得られるまでは判定を保留 |

### AI Bulk Audit の現実的な歩留まり

Chainlink V2 での実績:
- **2,000件** bulk audit → 104 applicable → 17 high confidence → **1件のみ有効 (M-15)**
- 有効率: **0.05%**。全件をコード上で検証する工程が必須

---

## 5. コードベース防御パターン（Chainlink V2）

1. **`s_entered` reentrancy guard** — `bid()` と `isValidSignature()` の両方をガード
2. **`assetOutAmount` をcallback前に確定** — callback 中の価格操作不可
3. **`safeTransferFrom` で atomic 支払い強制**
4. **SafeERC20 一貫使用**
5. **`AccessControlDefaultAdminRules`**
6. **`whenNotPaused` が全 critical path に適用**
7. **Constructor-based (non-upgradeable)**
8. **GPv2 `domainSeparator` + `filledAmount`** — EIP-1271 replay 防止
9. **`_whenNoLiveAuctions()` modifier**
10. **Oracle decimals 正規化**
11. **`isValidSignature()` settlement 時検証**
12. **`mulDivUp` 一貫使用** — 丸めがプロトコル有利（bidder が多く支払う方向）

---

## 6. Finding 別レビューサマリー

### 提出済み（C4に実提出）

| ID | Severity | 人手修正 |
|----|----------|---------|
| **H-01** | High | grandchildrice 7点FB → Medium→High、trust boundary明示 |
| **M-03** | Medium-High | grandchildrice valid判定 |
| **M-01** | Medium | pipeline発見、人手確認済み |
| **M-15** | Low | **PoC 全書き換え**: mock→code walkthrough、「5x loss」削除 |
| **M-02** | Low | grandchildrice「Low寄り」→ downgrade |

### 未提出

| ID | Severity | 理由 |
|----|----------|------|
| **M-08** | Low-Medium | narrow scope なら可。「永久凍結」は盛りすぎ |
| **M-07** | Low | trusted path (PRICE_ADMIN) |
| **M-14** | Low | residual ≈ 0、prior art不一致 |

### 却下

| ID | 却下理由 |
|----|---------|
| **C-01** | H-01 と同一 root cause |
| **M-04** | AUCTION_WORKER trusted |
| **M-05** | 非経済的（gas > profit） |
| **M-06** | AuctionBidder self-protect |
| **M-09** | 実害立証なし |
| **M-10** | config mismatch / 運用問題 |
| **M-11** | M-01/M-03 の言い換え |

---

## 7. 人手修正の全記録

| 修正 | Before (AI) | After (Human) | Commit |
|------|-------------|---------------|--------|
| H-01 Severity | Medium | **High** | ec13043f |
| H-01 Title | 「arbitrary call の亜種」 | 「trust boundary bypass」 | ec13043f |
| H-01 Impact | 「全トークン drain」 | 「_multiCall 中に approve したもののみ」 | ec13043f |
| M-15 PoC | mock test + console2.log | **code walkthrough** | fd326f4b |
| M-15 Impact | 「5x loss」テーブル | 「degree depends on divergence」 | fd326f4b |
| M-02 Severity | Medium | **Low** | 681c979c |
| M-07 Severity | Medium | **Low** | 681c979c |
| M-14 Severity | Medium | **Low** | 4522baaa |
| M-08 Scope | 「permanent freeze」 | 「stuck + config lockout」 | a1e66286 |
| M-06 判定 | Medium | **QA (hinin)** | b9ea01fe |

---

## 8. 次回監査への適用ルール

1. **Finding 生成後、提出前に必ずこの判定基準で self-review する**
2. **Permissionless trigger がない finding は Low 以下でスタート**
3. **Impact 表現は narrow scope で書き、recovery path を明記**
4. **同一 root cause の finding は 1 件にまとめる**
5. **Prior art 引用時は trust model の一致を確認**
6. **PoC は攻撃成功時に PASS する forge test で提出。mock で証明不能なら code walkthrough**
7. **Severity は全 artifacts で統一**
8. **AI出力は必ず人手検証。特に severity, impact, PoC assertion を重点チェック**
9. **経済的合理性を必ず確認（gas cost vs profit）。コスト > 利益は報告するが提出保留**
10. **2パスの非対称性は自動的に vulnerability ではない**
11. **efficiency parameter と security mechanism を区別する**
12. **タイトルで impact を誇張しない**
13. **前提条件が2つ以上の稀な条件の同時成立を要求していないか確認**
14. **Admin操作が前提なら通常運用で起こりうるかフィルタ**
15. **HIGH 探索は過去 CSV パターンマッチが最も効率的**
16. **C/C++ OSS レビュー時は最新ブランチでバグ残存を必ず確認してから PR 投稿**
17. **他モデルの human review 結果と相互参照して判定の信頼度を向上させる**
18. **GT 外の新発見は「GT にない = FP」ではなく、コードの実態で判定する**
19. **メンテナからのレビューFBには迅速に対応（NULL→nullptr 等のスタイル修正含む）**
