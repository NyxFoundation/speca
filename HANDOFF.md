# セキュリティ監査 引き継ぎドキュメント

**作成日:** 2026-04-08
**対象期間:** 2026-04-05 〜 2026-04-07

---

## 1. 対象リポジトリと成果物

| リポジトリ | 技術スタック | レポートPR | 修正PR | 監査方法 |
|---|---|---|---|---|
| ganondorofu/stem-system | Next.js 15 + Supabase + Discord OAuth | [#6](https://github.com/ganondorofu/stem-system/pull/6) | [#7](https://github.com/ganondorofu/stem-system/pull/7) | SPECA + 手動 + 実環境検証 |
| ganondorofu/stem-bot-v2 | Express.js 5.1 + Bearer Token Auth | [#1](https://github.com/ganondorofu/stem-bot-v2/pull/1) | [#2](https://github.com/ganondorofu/stem-bot-v2/pull/2) | SPECA + 手動 |
| ganondorofu/kintai-v3 | Next.js 15 + Supabase + NFC/QR/OAuth | [#10](https://github.com/ganondorofu/kintai-v3/pull/10) | [#11](https://github.com/ganondorofu/kintai-v3/pull/11) | SPECA + 手動 + 実環境検証 |
| penti-nameko/website | 静的サイト + ArgoCD + K8s | [#4](https://github.com/penti-nameko/website/pull/4) | [#5](https://github.com/penti-nameko/website/pull/5) | 手動 + CVE/実例ベース再監査 |

### PR投稿元

- Fork: `hirorogo/*` → Upstream: `ganondorofu/*` / `penti-nameko/*`
- 全PRから AI 痕跡（Co-Authored-By、Generated with Claude Code 等）は除去済み

---

## 2. 発見した脆弱性サマリ

### stem-system（16件確認 + 10件潜在）

| 深刻度 | 件数 | 代表的な問題 |
|--------|------|-------------|
| Critical | 3 | OAuth RPC 認証バイパス → アカウント乗っ取り、JWT_SECRET ハードコードフォールバック |
| High | 4 | TOCTOU（認可コード再利用）、redirect_uri 未検証、スコープインジェクション |
| Medium | 8 | Server Actions 入力検証不足、認証チェック欠如 |
| Low | 5 | debug エンドポイント残存、ログ過剰出力 |

### stem-bot-v2（14件確認 + 12件潜在）

| 深刻度 | 件数 | 代表的な問題 |
|--------|------|-------------|
| Critical | 1 | 任意 Discord ロール付与・剥奪（ロール検証なし） |
| High | 3 | Bearer トークンのタイミング非安全比較、CORS ワイルドカード |
| Medium | 6 | 入力検証不足、/health での情報漏洩 |
| Low | 4 | エラーメッセージ詳細露出、ページネーションなし |

### kintai-v3（40件確認 + 10件潜在）

| 深刻度 | 件数 | 代表的な問題 |
|--------|------|-------------|
| Critical | 5 | anon RPC 全公開（OAuth 乗っ取り）、is_admin 自己昇格、force-logout-all 認可不備 |
| High | 8 | 21件のNFCカードID漏洩（実データ確認済）、出勤偽造、IDOR |
| Medium | 15 | デバッグログ PII 漏洩、認証チェック欠如 |
| Low | 12 | TOCTOU、ログ過剰 |

**根本原因:** `ALTER DEFAULT PRIVILEGES IN SCHEMA member GRANT ALL ON FUNCTIONS TO anon`

### website（17件確認）

| 深刻度 | 件数 | 代表的な問題 |
|--------|------|-------------|
| Critical | 1 | IngressNightmare（CVE-2025-1974）※クラスタ構成依存 |
| High | 4 | securityContext 未設定、git-sync コマンドインジェクション、ArgoCD 権限昇格 |
| Medium | 7 | リソース制限なし、NetworkPolicy なし、セキュリティヘッダー欠如 |
| Low/Info | 5 | noopener なし、重複ファイル、Math.random() |

---

## 3. 実環境で確認したデータ漏洩

### 抽出した認証情報

- **Supabase URL:** `https://ptmcttcxlslguwbexifq.supabase.co`
- **Anon Key:** Next.js クライアントバンドル `/_next/static/chunks/` から抽出
- 3スキーマ（member/attendance/oauth）× 計45エンドポイントを列挙

### 実際に漏洩を確認したデータ

| データ | 件数 | 取得方法 |
|--------|------|----------|
| NFC カードID + QR トークン | 21件 | `attendance.temp_registrations` への anon SELECT |
| OAuth アプリ情報 | 全件 | `list_applications` RPC（anon key） |
| 認可コード作成 | 成功 | `create_authorization_code` RPC（anon key、戻り値 `true`） |
| 出勤記録偽造 | 可能 | `record_attendance_by_card` RPC（漏洩したカードIDで） |

---

## 4. 修正内容サマリ

### stem-system

- JWT_SECRET フォールバック削除（環境変数必須化）
- OAuth スコープホワイトリスト検証
- redirect_uri を登録済み許可リストと照合
- 認可コード即時削除（TOCTOU 対策）
- Server Actions に Zod 入力検証 + 認証チェック
- debug エンドポイント削除

### stem-bot-v2

- `crypto.timingSafeEqual` に変更
- DB ベースのロール許可リストで検証
- CORS ワイルドカード廃止
- /health レスポンス最小化
- 全 API に入力バリデーション追加
- ページネーション追加

### kintai-v3

- **DB マイグレーション 2本:**
  - `20260405000000_fix_is_admin_self_escalation.sql` — WITH CHECK で is_admin 書き換え防止
  - `20260405000001_fix_rpc_anon_access.sql` — anon の DEFAULT PRIVILEGES revoke + 全 RPC から EXECUTE revoke + レート制限追加
- **アプリ層:**
  - `auth-guard.ts` 新規作成（requireAdmin, requireAuth, checkRateLimit）
  - 管理者専用関数全てに認証チェック追加
  - デバッグログから PII 除去
  - Discord サーバー所属チェック再有効化

### website

- 全 Deployment に securityContext + リソース制限追加
- NetworkPolicy 追加（全3サイト）
- ssl-redirect アノテーション追加
- CDN リンクに SRI + noopener 追加
- nginx イメージ固定（alpine → 1.27-alpine）
- **注意:** nginx ConfigMap へのセキュリティヘッダー追加は意図的に見送り。運用上の理由で元の設定を維持。CSP等のヘッダーは別途 ingress-nginx の ConfigMap またはアノテーションで対応を推奨。

---

## 5. SPECA パイプライン詳細分析

### パイプライン全体のファネル

各リポジトリにおけるフェーズ間のアイテム数推移：

```
stem-system:   01e(224) → 02c(136) → 03(186) → 04(80)
stem-bot-v2:   01e(140) → 02c( 90) → 03( 90) → 04(90)
kintai-v3:     01e(204) → 02c(204) → 03(227) → 04(53)
```

**ファネルの読み方:**
- 01e→02c の減少: Phase 02c の Severity gate が `Informational` を除外
- 02c→03 の増減: Phase 03 が1プロパティから複数 audit_result を生成する場合あり（kintai-v3 で 204→227）
- 03→04 の減少: stem-system と kintai-v3 で Phase 04 の処理対象が大幅減。理由は Phase 03 で `out-of-scope` 判定されたものが多数あり、Phase 04 で `PASS_THROUGH` として自動スキップされるため

### Phase 04 判定結果の分布

| 判定 | stem-system | stem-bot-v2 | kintai-v3 | 説明 |
|------|-------------|-------------|-----------|------|
| CONFIRMED_VULNERABILITY | 17 | 14 | 40 | 実在する脆弱性。3ゲート全通過 |
| CONFIRMED_POTENTIAL | 10 | 12 | 10 | 潜在的リスク。条件次第で顕在化 |
| DISPUTED_FP | 0 | 5 | 2 | 偽陽性。ゲートで棄却 |
| NEEDS_MANUAL_REVIEW | 0 | 0 | 1 | 自動判定不能。人間の確認が必要 |
| PASS_THROUGH | 53 | 59 | 0 | Phase 03 で out-of-scope 判定済み |

**FP 率:** stem-bot-v2: 5/31 (16.1%), kintai-v3: 2/53 (3.8%)
（PASS_THROUGH を除いた実質レビュー対象に対する FP 率）

### NEEDS_MANUAL_REVIEW の詳細（kintai-v3: 1件）

- **PROP-attendanceze-pre-007** (High)
- Phase 03 の証明トレースが現行コードと矛盾: route.ts L123-143 では member.members を確認し未登録ユーザーをサインアウトしているが、Phase 03 はこのチェックを無視した証明を生成
- `registerNewMember` 関数がコードベースに存在しない（Gate 1 に近いが、本体の認証フロー自体は実在するため DISPUTED ではなく NEEDS_MANUAL_REVIEW）
- **対処:** 手動でコードを確認し、auth callback の認証フローが正しく実装されているか検証すること

---

## 6. FP 分析：なぜ偽陽性が発生したか

### 全 FP アイテム一覧

全7件の DISPUTED_FP は **全て Gate 1（Dead Code / コード不在）** で棄却された。Gate 2（Trust Boundary）や Gate 3（Scope Check）で棄却されたものはゼロ。

#### stem-bot-v2 の FP（5件）

| FP ID | 参照したパス | 実際の構造 | Phase 04 の棄却理由 |
|-------|-------------|-----------|-------------------|
| PROP-api-request-inv-007 | `src/lib/actions/members.ts::updateMemberAdmin` | `src/api/`, `src/middleware/` | `src/lib/` ディレクトリ不在 |
| PROP-stem-bot-v21-inv-002 | `src/lib/actions/teams.ts::createTeam` | 同上 | `src/lib/actions/` 丸ごと不在 |
| PROP-api-request-inv-015 | `src/api/rolesSync.ts::syncRoles` | `src/api/roles.ts` に統合 | ファイル・関数ともに不在 |
| PROP-api-request-pre-004 | `src/lib/actions/members.ts::registerNewMember` | 同上 | ファイル自体が不在 |
| PROP-docker-compo-inv-006 | `src/lib/actions/` 配下の `updateGenerationRoles` | 同上 | 関数・ディレクトリ不在 |

#### kintai-v3 の FP（2件）

| FP ID | 参照したパス | 実際の構造 | Phase 04 の棄却理由 |
|-------|-------------|-----------|-------------------|
| PROP-e5782b58-inv-008 | `src/lib/actions/members.ts::registerNewMember` (L284-326) | `src/lib/services/registration.service.ts` | ファイル不在。実装は別ファイルに統合済み |
| PROP-e5782b58-inv-014 | 同上（discord_uid インジェクション） | 同上 | 同上。さらにスキーマが異なり攻撃シナリオ不成立 |

### FP の根本原因

**Phase 01e（プロパティ生成）が仕様書から推測したファイルパスが、実際のコードベース構造と不一致。**

具体的なメカニズム：
1. Phase 01a がスペックURL（README、API ドキュメント等）をクロール
2. Phase 01b がスペックからサブグラフを抽出
3. Phase 01e がサブグラフを見て「このAPIには `src/lib/actions/members.ts` のような実装があるはず」と推測
4. しかし stem-bot-v2 は Express.js のフラットな構造（`src/api/`, `src/middleware/`）であり、Next.js 風の `src/lib/actions/` は存在しない
5. Phase 02c（コード事前解決）で Tree-sitter MCP を使って解決を試みるが、存在しないパスは解決できない
6. Phase 03 が解決できなかったパスに対して証明トレースを生成 → 当然、実在しないコードへの指摘になる
7. Phase 04 の Gate 1 で grep/find して不在を確認し、DISPUTED_FP

**つまり FP はパイプラインの上流（01e）で発生し、下流（04）で検出される。**

### CONFIRMED vs DISPUTED_FP の判定差の具体例

**CONFIRMED の典型的な reviewer_notes:**
```
All 3 gates passed.
Gate 1: removeRole is a live exported route handler registered at
POST /api/roles/remove (index.ts:71) — public API, passes regardless
of internal caller count.
Gate 2: BUG_BOUNTY_SCOPE.json contains no trust_assumptions field;
the entry point is the external REST API (no trusted caller).
Gate 3: src/api/ is explicitly in scope.
→ Severity: Critical
```

**DISPUTED_FP の典型的な reviewer_notes:**
```
Gate 1 (Dead Code / Code Does Not Exist):
The cited code path `src/lib/actions/members.ts::updateMemberAdmin`
does not exist in target repo `stem-bot-v2`. No `src/lib/` directory
exists; the repo uses `src/api/`, `src/middleware/`, etc.
→ DISPUTED_FP
```

**判定の境界線:**
- Gate 1 が通る条件: `grep -r "関数名"` でヒットし、かつテストファイル以外に呼び出し元がある
- Gate 1 で落ちる条件: ファイルパスまたは関数名が実在しない
- NEEDS_MANUAL_REVIEW になる条件: コード自体は存在するが、Phase 03 の証明トレースが現行コードと矛盾する（kintai-v3 の PROP-attendanceze-pre-007 がこの例）

---

## 7. セルフチェック基準（FP を減らすための実践ガイド）

Phase 04 の 3-gate FP フィルタを人間が再現する形で整理。
**今回の全 FP が Gate 1 で検出されたため、Gate 1 チェックが最重要。**

### チェック 1: コード存在確認（Gate 1 対策）— 最重要・最優先

今回の FP の **100% がこのチェックで検出可能** だった。

```
必須チェック項目:
□ 1-1. 指摘されたファイルパスが実際に存在するか？
       → grep / find / ls で確認。存在しなければ即 FP
□ 1-2. 指摘された関数名がコードベースのどこかに存在するか？
       → grep -r "関数名" src/ で確認
□ 1-3. 指摘された行番号がファイルの実際の行数範囲内か？
       → wc -l でファイルの行数を確認
□ 1-4. ディレクトリ構造の想定がリポジトリの実際の構造と一致するか？
       → tree src/ -d で実際の構造を確認
```

**具体的な落とし穴（今回の事例から）:**

| 仕様から推測されたパス | 実際のパス | フレームワーク |
|----------------------|-----------|--------------|
| `src/lib/actions/members.ts` | `src/api/members.ts` | Express.js |
| `src/lib/actions/teams.ts` | なし（チーム機能未実装） | Express.js |
| `src/api/rolesSync.ts` | `src/api/roles.ts` | Express.js |
| `src/lib/actions/members.ts` | `src/lib/services/registration.service.ts` | Next.js |

**パターン:** SPECAは Next.js の `src/lib/actions/` 構造を好んで推測する傾向がある。
Express.js やフラットな構造のリポジトリでは特に注意。

### チェック 2: 攻撃シナリオの実現可能性

```
□ 2-1. 攻撃の前提条件は現実的か？
       ・認証なしで到達可能か？
       ・認証済みユーザーなら誰でも可能か？
       ・管理者権限が必要か？（管理者の悪意は通常スコープ外）
□ 2-2. データフローを実コードで追跡できるか？
       ・入力 → 処理 → 出力の各ステップが実際のコードに対応するか
       ・途中にバリデーション/サニタイゼーションが挟まっていないか
□ 2-3. フレームワークの自動防御が効いていないか？
       ・Next.js: Server Actions の CSRF トークン自動付与
       ・Supabase: RLS（Row Level Security）ポリシー
       ・Express.js: helmet ミドルウェア等
□ 2-4. Phase 03 の証明トレースと現行コードが一致するか？
       ・Phase 03 が「このコードにはチェックがない」と言っている箇所を実際に開いて確認
       ・コードが更新されて既に修正済みの場合がある
```

**今回の教訓:**
- kintai-v3 の NEEDS_MANUAL_REVIEW（PROP-attendanceze-pre-007）は、Phase 03 がコードの一部（auth callback のメンバーチェック）を見落として証明を生成した例
- 「Phase 03 の証明が正しいか」を現行コードで必ず再確認すること

### チェック 3: 重複・根本原因の統合

```
□ 3-1. 同じ根本原因の指摘が複数出ていないか？
       ・kintai-v3 では DEFAULT PRIVILEGES が根本原因で 40件の
         CONFIRMED_VULNERABILITY が出た。修正は SQL マイグレーション 1本
□ 3-2. 1つの修正で何件の指摘が解消されるかを見積もる
       ・修正PR作成時は根本原因ごとにまとめる
□ 3-3. 異なるプロパティIDで同じコード箇所を指している指摘がないか
       ・Phase 01e が同じ機能に対して複数プロパティを生成することがある
```

**根本原因の統合例（kintai-v3）:**
```
40件の CONFIRMED_VULNERABILITY
  └─ 根本原因: ALTER DEFAULT PRIVILEGES ... GRANT ALL ON FUNCTIONS TO anon
     └─ 修正: 20260405000001_fix_rpc_anon_access.sql（1ファイル）
        ├─ anon の DEFAULT PRIVILEGES を REVOKE
        ├─ 全 RPC から anon の EXECUTE を REVOKE
        └─ 必要な関数のみ再 GRANT
```

### チェック 4: バグバウンティスコープ確認（Gate 3 対策）

```
□ 4-1. BUG_BOUNTY_SCOPE.json で明示的に除外されていないか？
□ 4-2. 管理者の悪意ある操作を前提としていないか？（centralization risk）
□ 4-3. 外部依存（npm パッケージ、Docker イメージ）の脆弱性で
       対象リポジトリ側で修正不可能なものではないか？
□ 4-4. テストコード、CI 設定、ドキュメントのみに影響する指摘ではないか？
```

### チェック 5: 環境差異

```
□ 5-1. 環境変数の有無で挙動が変わる箇所か？
       ・JWT_SECRET のハードコードフォールバック（stem-system で発見）
       ・NODE_ENV による分岐
□ 5-2. Supabase の anon key は本番環境で抽出可能か？
       ・Next.js の場合、クライアントバンドルに含まれるため常に抽出可能
       ・NEXT_PUBLIC_ プレフィックスの環境変数はすべて公開される
□ 5-3. ネットワーク構成に依存する脆弱性は別途マークする
       ・IngressNightmare は ingress-nginx のバージョン依存
       ・cert-manager HTTP-01 はクラスタ内の他テナントの存在依存
```

### チェックの優先順序フローチャート

```
SPECA の指摘を受け取った
  │
  ├─→ チェック 1: ファイル/関数は存在するか？
  │     NO → FP（今回の全 FP はここで検出）
  │     YES ↓
  │
  ├─→ チェック 4: スコープ内か？
  │     NO → スコープ外として除外
  │     YES ↓
  │
  ├─→ チェック 2: 攻撃シナリオは実現可能か？
  │     NO → FP or DOWNGRADE
  │     YES ↓
  │
  ├─→ チェック 3: 同じ根本原因の重複はないか？
  │     YES → 統合して1件にまとめる
  │     NO ↓
  │
  └─→ CONFIRMED として報告 + チェック 5 で環境依存をマーク
```

---

## 8. SPECA パイプライン実行メモ

### 環境設定

```bash
# Windows cp932 問題の回避（必須）
export PYTHONUTF8=1

# 並列実行時はワーカー数を制御（APIレート制限対策）
# 2ターゲット同時の場合は各1ワーカー推奨
# 単体実行の場合は4ワーカーまでOK

# 出力ディレクトリの分離
export SPECA_OUTPUT_DIR=outputs_<target-name>
# または --output-dir フラグ
```

### よくあったエラーと対処

| エラー | 原因 | 対処 |
|--------|------|------|
| `UnicodeDecodeError: cp932` | Windows Python のデフォルトエンコーディング | `PYTHONUTF8=1` |
| `UnicodeEncodeError: cp932 (emoji)` | サマリ出力のチェックマーク絵文字 | 実害なし（Phaseは完了済み） |
| `01b loaded 0 items` | STATE ファイルのフォーマット不一致 | `found_specs[].url` 形式に変換 |
| API 429 | 並列数過多 | ワーカー数削減 or 順次実行 |
| PR body too long | GitHub 65536文字制限 | `--body-file` フラグ使用 |

### Phase 01a STATE 形式の注意点

stem-bot-v2 で発生した問題：01a が `specs[].source` 形式で出力したが、
01b は `found_specs[].url` を期待。手動変換が必要だった。

Phase 間のデータ受け渡しで形式不一致が起きた場合は、
`scripts/orchestrator/schemas.py` のPydanticモデルを確認して手動変換する。

---

## 9. 手動監査で SPECA が見逃したもの

SPECA パイプラインだけでは検出できず、手動監査で発見した脆弱性：

### stem-system
- **JWT_SECRET ハードコードフォールバック**: コード中に `process.env.JWT_SECRET || "fallback-secret"` というパターンがあった。SPECA は環境変数のフォールバック値を静的解析しない
- **debug エンドポイント**: 開発用の `/api/debug/*` が残存。SPECA はエンドポイントの「本番不要」判定を行わない

### kintai-v3
- **実環境データ漏洩の検証**: anon key でのRPC呼び出しテスト（21件のNFCカードID漏洩確認）は手動で実施。SPECA は実際のAPIコールを行わない
- **DEFAULT PRIVILEGES の根本原因特定**: SPECA は個別のRPC関数ごとに脆弱性を報告したが、根本原因が1行の `ALTER DEFAULT PRIVILEGES` にあることの特定は手動分析

### website
- **CVE ベースの攻撃チェーン構築**: IngressNightmare (CVE-2025-1974)、git-sync コマンドインジェクション（Akamai DEF CON 2024）等は、既知の脆弱性データベースと実際の構成を突き合わせる手動作業
- **ArgoCD 自動同期のリスク評価**: `prune: true` + `selfHeal: true` + 公開リポジトリの組み合わせが攻撃チェーンの起点になることの指摘は手動

**教訓:** SPECA はコードレベルの脆弱性検出に強いが、以下は手動が必要：
1. 環境変数/設定のセキュリティ評価
2. 実環境でのデータ漏洩検証
3. インフラ構成（K8s、ArgoCD）のリスク評価
4. 既知 CVE との突き合わせ
5. 複数の脆弱性を連鎖させた攻撃チェーンの構築

---

## 10. ICU PR レビュー

別件で [unicode-org/icu#3913](https://github.com/unicode-org/icu/pull/3913) のレビューも実施。
`TransliteratorAlias` の use-after-free レースコンディション修正。英語でレビューコメント投稿済み。

修正内容: `adoptingAlias(alias)` → `cloneAlias(*alias)` で所有権セマンティクスを修正。
raw pointer（借用）から clone（所有）に変更し、元オブジェクトの lifetime に依存しなくなった。

---

## 11. 残作業・今後の推奨

### 即時対応が必要

- [ ] **kintai-v3 DB マイグレーション適用** — 本番 Supabase に2本のマイグレーションを適用（anon RPC 漏洩が現在進行形）
  - `20260405000000_fix_is_admin_self_escalation.sql`
  - `20260405000001_fix_rpc_anon_access.sql`
  - 適用順序は番号順。ロールバックが必要な場合に備えてバックアップを取ること
- [ ] **stem-system のJWT_SECRET 確認** — 本番環境の環境変数が正しく設定されているか確認。フォールバック値が使われている場合、全セッションが危殆化
- [ ] **全リポの main ブランチ保護** — PR レビュー必須化（特に website は ArgoCD 自動同期のため、main への直接 push = 即座に本番反映）

### 中期的

- [ ] 各 PR のレビュー・マージ
- [ ] website の ingress-nginx バージョン確認（CVE-2025-1974 対応済みか）
- [ ] ArgoCD の Project 設定確認（`clusterResourceBlacklist` 等）
- [ ] Supabase anon key のローテーション検討（漏洩データ確認済みのため）
- [ ] Google Fonts のセルフホスト化（SRI が使えないため）
- [ ] website の nginx ConfigMap にセキュリティヘッダー追加（今回は見送ったが、CSP・X-Frame-Options 等の導入を推奨）

### 長期的

- [ ] SPECA パイプラインの定期実行（コード変更時の回帰チェック）
- [ ] コンテナイメージの SHA256 ダイジェスト固定
- [ ] CSP ヘッダーの本格導入
- [ ] cert-manager の DNS-01 チャレンジへの切り替え検討
