# SPECA CI ツール化 要件定義書

> **目的:** して、SPECA を任意の CI 環境に統合可能な1コマンドツールにする。
> **バージョン:** 2.0 (SaaS モデル採用)
> **最終更新:** 2026-04-16

---

## 0. エグゼクティブサマリ

本リポジトリには既に 2 つの「入力 → 成果物返却」フローが存在する:

1. **`.github/workflows/full-audit.yml`** — `workflow_dispatch` にパラメータを送るとパイプライン全体が走り結果ブランチが作られる
2. **Web クライアント (PR #100)** — Web フォームから上記ワークフローを起動し、ユーザーはプロンプト等の中身を一切見ない

**本 RFC のゴール:** Web クライアントが実現している「中身を見せずに結果だけ返す」パターンを、**CI ツール版**として切り出す。どの CI (GitHub Actions / GitLab CI / CircleCI / Jenkins / ローカル) からでも 1 コマンドで呼び出せ、SARIF/JSON が返る。

> **プロダクトの本体は `speca` CLI / Docker イメージ (CI 非依存)**。
> GitHub Action 等は、それを呼ぶ薄いラッパーの 1 つに過ぎない。

### Web クライアントと CI ツールの構造対応

| | Web クライアント (既存) | **CI ツール (今回)** |
|---|---|---|
| ユーザー入口 | Web フォーム | CLI / Docker コマンド |
| 転送手段 | `workflow_dispatch` API | HTTPS REST API |
| 実行主体 | Nyx のプライベートリポで `full-audit.yml` | Nyx のバックエンドで同等パイプライン |
| ユーザーが見るもの | Findings のみ | Findings のみ (SARIF/JSON) |
| プロンプト・スキル・DB | **見えない** (private repo 内) | **見えない** (Nyx バックエンド内) |
| ローテ・暗号化・TEE | 不要 | 不要 |

---

## 1. ユーザーストーリー

### 1.1 プライマリユースケース (CI 非依存)

**任意のプロジェクトのメンテナとして、**
CI に `speca` を組み込むと:

1. PR またはコミット単位でターゲットコードと関連仕様を読み取り
2. 仕様逸脱・既知脆弱性パターン・STRIDE/CWE リスクを検出
3. SARIF / JSON / Markdown で結果を出力
4. 深刻度閾値を超える findings があれば exit code 1 で CI を失敗させる

### 1.2 ユースケース例

| ユーザー | ユースケース | 想定 CI |
|---|---|---|
| Ethereum Foundation (最初のパイロット) | `execution-specs` / `reth` 等の PR ごと監査 | GitHub Actions |
| DeFi プロトコルチーム | Solidity 変更前の自動監査 | GitHub Actions / GitLab CI |
| 監査会社 | コンテスト支援・プレ監査 | ローカル CLI |
| エンタープライズ | 内部 Jenkins パイプラインへの組込 | Jenkins |
| 個人監査人 | ラップトップで手元実行 | ローカル CLI |

※ EF グラントでの最初のパイロット先は Ethereum 関連だが、**プロダクト自体は汎用 CI ツール**。

---

## 2. 成果物と配布形態

| ID | 成果物 | 配布先 | ライセンス |
|---|---|---|---|
| D1 | `speca` CLI (Python パッケージ) | PyPI `speca` | Apache-2.0 (外殻) |
| D2 | `speca` Docker イメージ | `ghcr.io/nyxfoundation/speca:v1` | Apache-2.0 |
| D3 | Nyx バックエンド API (実行基盤) | Nyx 自己ホスト | **Proprietary (非公開)** |
| D4 | GitHub Action ラッパー (例) | `nyxfoundation/speca-action@v1` | Apache-2.0 |
| D5 | GitLab CI テンプレート・CircleCI Orb (例) | 各マーケットプレイス | Apache-2.0 |
| D6 | EF パイロットリポ統合 PR | EF 側リポ | — |
| D7 | ベンチマーク・論文 | arXiv | CC-BY-4.0 |
| D8 | セキュリティ保証書 (脅威モデル) | EF 提出 | — |

---

## 3. ユーザー体験 (UX)

### 3.1 共通: 必要な Secret

CI の secret に以下を登録:

```
SPECA_API_KEY = spc_xxxxx   # Nyx から発行
```

これだけ。Anthropic API キーは Nyx 側で管理する (グラント枠) ので、EF は持つ必要なし。

### 3.2 GitHub Actions

```yaml
# .github/workflows/speca.yml
on: [pull_request]
jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: nyxfoundation/speca-action@v1
        with:
          api-key: ${{ secrets.SPECA_API_KEY }}
          spec-urls: https://eips.ethereum.org/EIPS/eip-7702
          mode: incremental
```

### 3.3 GitLab CI

```yaml
speca:
  image: ghcr.io/nyxfoundation/speca:v1
  script:
    - speca scan
        --repo=$CI_PROJECT_PATH
        --commit=$CI_COMMIT_SHA
        --spec-url=https://eips.ethereum.org/EIPS/eip-7702
        --api-key=$SPECA_API_KEY
        --output=findings.sarif
  artifacts:
    reports:
      sast: findings.sarif
```

### 3.4 CircleCI

```yaml
jobs:
  audit:
    docker:
      - image: ghcr.io/nyxfoundation/speca:v1
    steps:
      - run: speca scan --repo=<< pipeline.project.git_url >>
                        --commit=$CIRCLE_SHA1
                        --api-key=$SPECA_API_KEY
                        --output=findings.sarif
      - store_artifacts:
          path: findings.sarif
```

### 3.5 Jenkins (Declarative Pipeline)

```groovy
pipeline {
  agent any
  stages {
    stage('SPECA Audit') {
      steps {
        sh '''docker run ghcr.io/nyxfoundation/speca:v1 scan \
              --repo="${GIT_URL}" --commit="${GIT_COMMIT}" \
              --api-key="${SPECA_API_KEY}" --output=findings.sarif'''
        archiveArtifacts 'findings.sarif'
      }
    }
  }
}
```

### 3.6 ローカル CLI

```bash
pip install speca
speca scan --repo=ethereum/execution-specs --commit=abc123 \
           --spec-url=https://eips.ethereum.org/EIPS/eip-7702 \
           --api-key=$SPECA_API_KEY \
           --output=findings.sarif
```

### 3.7 出力

| 出力先 | 形式 | 用途 |
|---|---|---|
| SARIF ファイル | v2.1.0 | GitLab/GitHub Security UI / エディタ連携 |
| JSON ファイル | 独自形式 | 機械可読・長期保存 |
| Markdown ファイル | PR/MR コメント用 | サマリ表示 |
| Stdout (JSON stream) | 進捗・ライブ findings | リアルタイム監視 |
| Exit code | `0`=clean / `1`=findings≥threshold / `2`=tool error | CI ゲート |

---

## 4. アーキテクチャ

### 4.1 全体像

```
┌─────────────────────────────┐        ┌──────────────────────────────────┐
│ User's CI (任意環境)         │        │ Nyx Backend (private)             │
│                             │        │                                  │
│ ┌─────────────────────────┐ │        │ ┌──────────────────────────────┐ │
│ │ speca CLI / Docker       │ │ HTTPS │ │ API Gateway                   │ │
│ │                          │─┼───────►│ │   POST /v1/scans             │ │
│ │ 約 300 行の HTTP クライ   │ │        │ │   GET  /v1/scans/{id}        │ │
│ │ アント + SARIF 整形       │ │        │ │   GET  /v1/scans/{id}/results│ │
│ │                          │◄┼────────│ └──────────────────────────────┘ │
│ └─────────────────────────┘ │        │             ↓                    │
│                             │        │ ┌──────────────────────────────┐ │
│ 出力:                       │        │ │ Job Scheduler                │ │
│   findings.sarif            │        │ │ (Redis / PostgreSQL queue)   │ │
│   findings.json             │        │ └──────────────────────────────┘ │
│                             │        │             ↓                    │
└─────────────────────────────┘        │ ┌──────────────────────────────┐ │
                                       │ │ Worker Fleet                  │ │
                                       │ │ (security-agent を clone した │ │
                                       │ │  private repo を実行)         │ │
                                       │ │                              │ │
                                       │ │  ・ターゲットリポ clone       │ │
                                       │ │  ・full-audit.yml 相当を実行 │ │
                                       │ │    (01a → 04 パイプライン)   │ │
                                       │ │  ・Anthropic API 呼び出し    │ │
                                       │ │    (Nyx のキー, グラント枠)  │ │
                                       │ └──────────────────────────────┘ │
                                       │             ↓                    │
                                       │ ┌──────────────────────────────┐ │
                                       │ │ Result Store (S3 / DB)       │ │
                                       │ │   SARIF / JSON / ログ         │ │
                                       │ └──────────────────────────────┘ │
                                       └──────────────────────────────────┘
```

### 4.2 データフロー

| データ | 誰 → 誰 | 備考 |
|---|---|---|
| Scan request | User CI → Nyx API | `{repo, commit, spec_urls, scope}` |
| ターゲットコード | GitHub → Nyx Worker | Nyx が直接 git clone (パブリックリポの場合) |
| プロンプト・スキル・DB | Nyx 内部のみ | 外部に出ない |
| Anthropic 呼び出し | Nyx Worker → Anthropic | Nyx のキー使用 |
| Findings | Nyx → User CI | SARIF/JSON のみ |
| テレメトリ | User CI → Nyx | 使用量のみ (findings の統計は含まない) |

### 4.3 コンポーネント詳細

#### (A) `speca` CLI (OSS, Apache-2.0)

- Python 実装、`pip install speca`
- Docker イメージとしても配布 (`ghcr.io/nyxfoundation/speca:v1`)
- 役割:
  - 引数パース・設定読み込み (`.speca.yml`)
  - Nyx API への HTTPS リクエスト
  - ジョブ進捗ポーリング
  - SARIF/JSON/Markdown 整形・出力
  - Exit code 判定
- コードベース規模: 約 300〜500 行
- **内部ロジック (プロンプト等) は一切含まない** — 全て API 越し

#### (B) Nyx Backend (Proprietary)

- **API Gateway**: FastAPI / Cloudflare Workers
- **Job Queue**: Redis Stream / PostgreSQL LISTEN/NOTIFY
- **Worker Fleet**: Kubernetes Jobs / Fly Machines / AWS Batch
  - 各 Worker は `security-agent` リポ (private fork) をベースに動作
  - 既存の `full-audit.yml` 相当のパイプラインを内部実行
  - プロンプト・スキル・過去 DB は Worker ローカルに存在
- **Result Store**: S3 互換 (Cloudflare R2 / Wasabi) + PostgreSQL メタデータ
- **Anthropic API**: Nyx が直接契約、グラント枠で EF 負担ゼロ

#### (C) GitHub Action ラッパー (OSS)

- `action.yml` + `entrypoint.sh`
- 単に `docker run ghcr.io/nyxfoundation/speca:v1 scan ...` を実行
- GitHub イベント (`pull_request`, `push`) から自動的に `repo`/`commit`/`diff-base` を抽出
- 結果を GitHub Security タブに投稿

---

## 5. API 設計 (抜粋)

### 5.1 スキャン開始

```http
POST /v1/scans
Authorization: Bearer spc_xxxxx
Content-Type: application/json

{
  "target": {
    "repo": "ethereum/execution-specs",
    "commit": "abc123...",
    "scope": {
      "include": ["src/**/*.py"],
      "exclude": ["tests/**"]
    }
  },
  "spec": {
    "sources": ["https://eips.ethereum.org/EIPS/eip-7702"]
  },
  "mode": "incremental",
  "diff_base": "main",
  "gate": { "fail_on": "high" }
}
```

レスポンス:
```http
202 Accepted
{ "scan_id": "scn_xyz", "status_url": "/v1/scans/scn_xyz" }
```

### 5.2 進捗確認

```http
GET /v1/scans/scn_xyz
→ 200 OK
{
  "scan_id": "scn_xyz",
  "status": "running",
  "progress": 0.42,
  "phase": "03_audit_map",
  "partial_findings_count": 3,
  "eta_seconds": 245
}
```

### 5.3 結果取得

```http
GET /v1/scans/scn_xyz/results?format=sarif
→ 200 OK
Content-Type: application/sarif+json

{ "version": "2.1.0", "runs": [...] }
```

---

## 6. 機密性 (秘匿) 要件

### 6.1 何を守るか

| 資産 | 秘匿手段 |
|---|---|
| プロンプト (01a〜04) | Nyx バックエンド内のみに存在、外部に出ない |
| スキル (spec-discovery 等) | 同上 |
| 過去 DB パターン | 同上 |
| 重大度キャリブレーション | 同上 |
| オーケストレーター内部ロジック | 同上 |
| **プロダクトの独自価値** | API 越しに結果だけ返すため **逆解析不可能** |

### 6.2 脅威モデル

| 脅威 | 対象 | 対策 |
|---|---|---|
| T1: プロンプト抽出攻撃 (findings からの逆推論) | 出力データ | 出力を必要最小限に絞る (内部 property ID をハッシュ化) |
| T2: Nyx バックエンドへの侵入 | プロンプト・DB | 一般的なセキュリティ対策 (IAM, 監査ログ, WAF) |
| T3: API キー流出 | スキャン枠の悪用 | 使用量上限 + 失効機能 + ログ監視 |
| T4: ターゲットコードの漏洩 | ユーザーのコード | TLS + 完了後自動削除 + 監査ログ |

### 6.3 Web クライアントと同じ秘匿性が得られる理由

Web クライアントは `workflow_dispatch` で Nyx の private repo 上でパイプラインを動かし、ユーザーは結果だけ見る構造。

CI ツールは HTTPS API で Nyx の private backend 上で同等のパイプラインを動かし、ユーザーは結果だけ見る構造。

**どちらも「実行環境が Nyx 側」であることが秘匿の源泉。** 暗号化・TEE・ローテといった複雑な仕組みは不要。

---

## 7. 機能要件 (Functional Requirements)

### FR-1: 実行モード

- **full mode**: リポ全体を監査 (週次・リリース前)
- **incremental mode**: `diff-base` からの変更ファイルに関連するプロパティのみ (PR ごと、< 10 分)
- **properties_only mode**: 仕様からプロパティ生成のみ

### FR-2: 入力

- ターゲットリポ (URL + commit SHA)
- 仕様 URL リスト (EIP / markdown / PDF)
- スコープ (glob include/exclude)
- 深刻度ゲート

### FR-3: 出力

- SARIF v2.1.0
- JSON (独自、機械可読)
- Markdown (人間可読)
- Stdout stream (ライブ進捗)
- Exit code 規約

### FR-4: プライベートリポ対応 (オプション機能)

パブリックリポは Nyx が直接 clone 可能。プライベートリポの場合:

- **Option A**: GitHub App 連携 (ユーザーが Nyx GitHub App をインストール、Nyx は OAuth トークンで一時 clone)
- **Option B**: ユーザー側で tar 化して API にアップロード (完了後自動削除)
- **Option C** (将来): On-premise エンタープライズ版 (暗号化 payload + Self-hosted Worker)

### FR-5: Ethereum 特化

- EIP 標準チェック (ERC-20/721/1155/4337)
- ハードフォーク仕様差分認識
- ビーコンチェーン特化プロパティ
- EL/CL クライアント特化 (reth / geth / prysm / lighthouse)

### FR-6: 決定論・再現性

- モデルバージョンピン
- LLM レスポンスキャッシュ (Nyx 側、同一入力で再実行時高速化)
- `replay` API で過去のスキャンを再実行

### FR-7: コスト制御

- スキャン単位で budget 設定可能
- 上限到達で即時中断、部分結果を返す

---

## 8. 非機能要件 (NFR)

| NFR | 目標 |
|---|---|
| NFR-1: incremental mode 実行時間 | < 10 分 |
| NFR-2: full mode 実行時間 | < 4 時間 |
| NFR-3: Issue Recall (Sherlock ベンチ) | ≥ 0.3 (現状 0.273) |
| NFR-4: FP Rate (Phase 04 後) | ≤ 20% |
| NFR-5: API 可用性 | 99.5% |
| NFR-6: CLI 起動時間 | < 3 秒 |
| NFR-7: SARIF 準拠 | v2.1.0 完全準拠 |
| NFR-8: CI 統合の最小記述 | 5 行以内 |

---

## 9. インフラ要件 (Nyx 側)

| コンポーネント | 技術候補 | 用途 |
|---|---|---|
| API Gateway | FastAPI + uvicorn on Fly.io | HTTPS エンドポイント |
| Job Queue | Redis Streams / Celery | 非同期ジョブ管理 |
| Worker Fleet | Kubernetes / Fly Machines / AWS Batch | パイプライン実行 |
| Worker Image | `security-agent` private fork | 現行コードそのまま流用 |
| Result Store | Cloudflare R2 / S3 | SARIF・ログ保存 |
| メタデータ DB | PostgreSQL | ジョブ状態・使用量 |
| 監視 | Grafana Cloud / Sentry | SLA 監視 |
| シークレット | HashiCorp Vault / AWS Secrets Manager | Anthropic キー等 |
| CDN | Cloudflare | API レイテンシ削減 |

---

## 10. マイルストーン

| M | 期間 | 目標 | 検証可能な成果 |
|---|---|---|---|
| **M1** | 2週 | Nyx API Gateway + Job Queue 最小構成 | `curl POST /v1/scans` が受理される |
| **M2** | 3週 | Worker で既存 `full-audit.yml` 相当を実行 | 1スキャンが通して完了する |
| **M3** | 2週 | `speca` CLI (Python, pip 配布) | `speca scan` で SARIF が返る |
| **M4** | 2週 | Docker イメージ + GitHub Action ラッパー | `uses: nyxfoundation/speca-action@v1` が動く |
| **M5** | 2週 | Incremental mode + diff 解析 + キャッシュ | PR 単位 < 10 分達成 |
| **M6** | 3週 | EF リポパイロット (`execution-specs` or `reth`) | 実 PR で監査・レポート提出 |
| **M7** | 2週 | GitLab CI / CircleCI / Jenkins のサンプル + ドキュメント | 複数 CI 統合デモ |
| **M8** | 2週 | Cosign 署名 + ベンチマーク論文 + EF 報告書 | グラント完了書類提出 |

**合計: 18 週 (約 4.5 ヶ月)**

---

## 11. 成功判定基準

### EF グラント成果としての定義
- [ ] EF 指定リポジトリ (少なくとも 1 つ) に `speca` が CI 統合され PR 単位で動作
- [ ] Issue Recall ≥ 0.3、FP Rate ≤ 20% 達成
- [ ] SARIF が各 CI の標準 UI (GitHub Security タブ / GitLab SAST レポート等) に表示
- [ ] 3 種類以上の CI (GitHub Actions / GitLab CI / ローカル CLI) で動作確認済み
- [ ] ベンチマーク論文 arXiv 投稿済み

### ユーザーとしての成功
- [ ] `docker run` or `uses:` 1 行で監査開始
- [ ] PR ごとに自動実行され、開発フローを阻害しない (< 10 分)
- [ ] 誤検知で CI が無駄に失敗しない (FP ≤ 20%)
- [ ] ツールの中身を一切意識する必要がない

---

## 12. リスクと緩和策

| リスク | 影響 | 緩和策 |
|---|---|---|
| R1: Nyx バックエンド障害 | 全ユーザーの CI が失敗 | マルチリージョン冗長化 + フェイルオープンオプション |
| R2: Anthropic API レートリミット | スキャン遅延 | Nyx 側で queue 管理 + バックオフ |
| R3: Claude モデル仕様変更 | 出力破綻 | モデルピン + 回帰テスト自動化 |
| R4: API キー流出 | スキャン枠悪用 | 使用量上限 + rate limit + 失効機構 |
| R5: プライベートリポ対応遅延 | エンタープライズ採用不可 | GitHub App 連携を M7 以降で追加 |
| R6: EF リポの clone 権限問題 | Nyx がパブリックリポを落とせない | GitHub トークン併用 + フォールバック tarball アップロード |
| R7: Nyx 運用コスト超過 | 持続可能性リスク | グラント期間中はグラント負担、以後は段階的課金検討 |

---

## 13. オープン課題

1. **パイロット先**: `execution-specs` と `reth` どちらを先に？
2. **プライベートリポ対応優先度**: M3 に前倒すか？ M7 で良いか？
3. **Anthropic API 負担**: 全面 Nyx 負担か、ユーザー提供 API キーでの動作モードも残すか？
4. **Result 保持期間**: SARIF/JSON は何日保存するか？ GDPR 対応?
5. **GitHub App の名前空間**: `nyxfoundation/speca-app` で良いか？
6. **18 週の開発体制**: 何人月か？ フロントエンド (ダッシュボード) は含めるか？

---

## 14. 参考情報

- 現行パイプライン: `scripts/orchestrator/`, `prompts/01*-04*.md`, `.github/workflows/full-audit.yml`
- Web クライアント (構造の元): PR #100 (`web/src/pages/AuditWizardPage.tsx`)
- 類似プロダクト: Snyk / Semgrep Cloud / Checkmarx One (SaaS 型セキュリティスキャナ)
- SARIF 仕様: https://sarifweb.azurewebsites.net/
- SLSA: https://slsa.dev/

---

## 15. 次のアクション

1. 本 RFC のレビュー・承認
2. **M1 着手**: Nyx API Gateway の最小スケルトン (`api/` ディレクトリ)
3. **M2 準備**: 現行 `full-audit.yml` を Worker image に内包する仕組みの設計
4. **M3 並行**: `speca` CLI の OSS リポジトリ分離検討 (`nyxfoundation/speca-cli`)
5. Nyx バックエンド用クラウドインフラ準備 (Fly.io / Cloudflare R2 等)

---

## 16. 旧モデル (暗号化 Payload + Self-hosted Worker) との比較

参考として、RFC v1.0 で検討していた「暗号化 Payload + Self-hosted Worker」モデルとの比較:

| 項目 | 旧モデル (暗号化 Payload) | **新モデル (SaaS)** |
|---|---|---|
| 実行場所 | ユーザー環境 | **Nyx バックエンド** |
| プロンプト秘匿 | 暗号化 + RAM 復号 + 月次ローテ | **サーバー側にのみ存在** |
| 実装複雑度 | 高 (Cosign / mlock / TEE 検討) | **低 (既存パイプラインをAPI越しに提供)** |
| ユーザーのコード流出リスク | なし (ローカル実行) | あり (Nyx 側で一時処理) → TLS + 自動削除 |
| Anthropic API 負担 | ユーザー | **Nyx** |
| ユーザーから中身抽出の困難さ | 中 (メモリダンプリスク) | **極めて困難** (API 越しのため) |
| 運用コスト | 低 (配信鯖のみ) | 中 (実行基盤必要) |
| パブリックリポ対応 | ✓ | ✓ |
| プライベートリポ対応 | ✓ (自動) | △ (GitHub App 連携等) |

**結論:** Ethereum のパブリックリポ前提なら SaaS モデルが優位。プライベートリポ対応が必須のエンタープライズ向けにのみ旧モデルを選択肢として残す (Section 17)。

---

## 17. 補足: オンプレミス版 (将来オプション)

プライベートコード・機密案件向けに、将来的にオンプレミス版を提供する場合:

- `speca-onprem` Docker イメージ
- 暗号化 Payload を Nyx 配信鯖からダウンロード
- ユーザー環境内で完結、コードも結果も外に出ない
- 月次ローテ + Cosign 署名 + (オプション) TEE

これは EF グラントのスコープ外。グラント完了後の商用オプションとして検討。
