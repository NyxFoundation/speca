# SPECA CI ツール化 要件定義書

> **目的:** Ethereum Foundation グラント (採択済) の成果物として、SPECA を EF の CI パイプラインに統合可能な1コマンドツールにする。
> **バージョン:** 1.0 (Draft)
> **最終更新:** 2026-04-16

---

## 0. エグゼクティブサマリ

研究用非同期パイプライン (`scripts/run_phase.py` + 6 フェーズ) として運用されている現行 SPECA を、**GitHub Action のワンライナーで動く CI ツール**に再構成する。EF 開発者は `speca-action@v1` を workflow に1行追加するだけで、仕様整合性監査・脆弱性検出・SARIF レポート生成が自動実行される。

検出ロジック（プロンプト・スキル・キャリブレーション）は**業界最高水準ツールとして逆解析攻撃から保護するため非公開**とし、Worker 外殻のみ OSS 公開する（Semgrep Pro / CrowdStrike / Cloudflare WAF と同じ方針）。

---

## 1. ユーザーストーリー

### 1.1 プライマリユースケース

**EF コントリビューターとして、**
PR を作成すると、SPECA が自動で:

1. 変更コードと関連仕様を読み取り
2. 仕様逸脱・既知脆弱性パターン・STRIDE/CWE リスクを検出
3. GitHub Security タブと PR コメントに結果を表示
4. High 深刻度以上があれば CI を失敗させる

**設定は GitHub Secrets に API キー2枚 + workflow に 6 行追加するだけ。**

### 1.2 対象 EF リポジトリ (パイロット候補)

| 優先度 | リポジトリ | 理由 |
|---|---|---|
| P0 | `ethereum/execution-specs` | 仕様駆動、Python、スコープ明確 |
| P0 | `paradigmxyz/reth` | Rust EL クライアント、活発 |
| P1 | `ethereum/consensus-specs` | CL 仕様 |
| P1 | `prysmaticlabs/prysm` | Go CL クライアント |
| P2 | `ethereum/go-ethereum` | Go EL クライアント |

---

## 2. 成果物と配布形態

| ID | 成果物 | 配布先 | ライセンス |
|---|---|---|---|
| D1 | `speca-worker` Docker イメージ | `ghcr.io/nyxfoundation/speca-worker:vX.Y.Z` | Apache-2.0 (外殻) |
| D2 | `speca-action` GitHub Action | `nyxfoundation/speca-action@v1` | Apache-2.0 |
| D3 | 暗号化 Payload (プロンプト・スキル・DB) | Nyx 配信鯖 (月次ローテ) | **Proprietary (非公開)** |
| D4 | EF リポジトリ統合 PR | EF 側リポジトリ | — |
| D5 | ベンチマーク・論文 | arXiv / EF レポート | CC-BY-4.0 |
| D6 | セキュリティ保証書 (脅威モデル) | EF 提出 | — |

---

## 3. ユーザー体験 (UX)

### 3.1 セットアップ (1回のみ)

```
GitHub Secrets に登録:
  ANTHROPIC_API_KEY = sk-ant-xxxxx   # EF が Anthropic と契約
  SPECA_LICENSE_KEY = spc_xxxxx      # Nyx から EF に発行
```

### 3.2 Workflow (最小構成、6 行)

```yaml
# .github/workflows/speca.yml
jobs:
  speca-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: nyxfoundation/speca-action@v1
        with:
          anthropic-key: ${{ secrets.ANTHROPIC_API_KEY }}
          license-key: ${{ secrets.SPECA_LICENSE_KEY }}
```

### 3.3 高度な設定 (オプション)

```yaml
- uses: nyxfoundation/speca-action@v1
  with:
    anthropic-key: ${{ secrets.ANTHROPIC_API_KEY }}
    license-key: ${{ secrets.SPECA_LICENSE_KEY }}
    spec-urls: |
      https://eips.ethereum.org/EIPS/eip-7702
      https://eips.ethereum.org/EIPS/eip-4844
    scope-include: "src/**/*.rs,crates/**/*.rs"
    scope-exclude: "**/test/**,**/mocks/**"
    mode: incremental          # full | incremental | properties_only
    diff-base: main            # incremental 時の比較元
    fail-on: high              # none | low | medium | high
    budget-usd: 50
    budget-minutes: 30
    output-format: sarif       # sarif | json | markdown
```

### 3.4 出力

| 出力先 | 形式 | 用途 |
|---|---|---|
| GitHub Security タブ | SARIF v2.1.0 | 脆弱性一覧・トリアージ |
| PR コメント | Markdown | 要約・インラインコメント |
| Workflow Artifact | `speca-findings.json` + `speca-findings.sarif` | ダウンロード・長期保存 |
| Exit code | `0`=clean / `1`=findings≥threshold / `2`=tool error | CI ゲート |

---

## 4. アーキテクチャ

### 4.1 全体像

```
┌───────────────────────────────────────────────┐        ┌──────────────────────┐
│ EF リポジトリ CI (GitHub-hosted runner)        │        │ Nyx 配信鯖           │
│                                                │        │ (小規模 VPS 1台)     │
│ ┌──────────────────────────────────────────┐  │        │                      │
│ │ speca-action (OSS, 約 100 行)             │  │        │ /v1/auth             │
│ │   ├─ inputs パース                        │  │        │ /v1/payload/latest   │
│ │   ├─ worker コンテナ起動                  │  │        │ /v1/telemetry        │
│ │   └─ 結果を GitHub API へ投稿             │  │        │                      │
│ └──────────┬───────────────────────────────┘  │        └──────────────────────┘
│            ↓                                   │                  ▲
│ ┌──────────────────────────────────────────┐  │                  │ HTTPS
│ │ speca-worker (Docker, Cosign 署名済)      │  │                  │
│ │   ├─ License 認証                         │──┼──────────────────┘
│ │   ├─ 暗号化 Payload ダウンロード           │←─┤
│ │   ├─ メモリ上で復号 (ディスク書き込み禁止) │  │                  ×
│ │   ├─ 対象リポを読み取り                    │  │    ❌ Nyx にコードは送信されない
│ │   ├─ Anthropic API 呼び出し                │──┼──► Anthropic
│ │   │  (EF の API キーで、EF が課金)         │  │
│ │   └─ Findings 生成 → SARIF 変換            │  │
│ └──────────┬───────────────────────────────┘  │
│            ↓                                   │
│   speca-findings.sarif (ローカル出力)         │
└───────────────────────────────────────────────┘
```

### 4.2 データフロー

| データ | 流れ | 秘匿 |
|---|---|---|
| EF のコード | EF CI ローカル → Anthropic (EF 契約) | Nyx に届かない |
| 仕様 URL | EF CI ローカル → Anthropic | Nyx に届かない |
| Payload (プロンプト等) | Nyx → Worker メモリ (暗号化) | 暗号化 + RAM のみ |
| Findings | Worker → GitHub Security タブ (ローカル) | EF ローカルのみ |
| テレメトリ | Worker → Nyx (使用量・成功失敗・所要時間) | コード/仕様は含まない |

### 4.3 コンポーネント詳細

#### (A) `speca-action` (OSS, Apache-2.0)

- `action.yml` + `entrypoint.sh`
- Docker ベース Action
- 入力検証・worker 起動・結果整形・GitHub API 投稿
- 約 100〜200 行

#### (B) `speca-worker` (OSS 外殻 + 非公開 Payload)

**OSS 部分 (Apache-2.0):**
- `entrypoint.py`: メインエントリ
- `license.py`: ライセンス認証・Payload 取得
- `crypto.py`: AES-256-GCM 復号
- `runner.py`: Anthropic SDK 呼び出しラッパー
- `sarif.py`: SARIF v2.1.0 エクスポート
- `diff.py`: incremental モード用 diff 解析

**非公開 Payload (暗号化):**
- プロンプト (01a〜04)
- スキル (spec-discovery, subgraph-extractor)
- 過去 DB (`past_defi_patterns.csv` 等)
- 重大度キャリブレーション・3ゲート FP フィルタロジック
- オーケストレーション制御パラメータ

#### (C) Nyx 配信鯖

- FastAPI + SQLite/PostgreSQL
- エンドポイント:
  - `POST /v1/auth`: ライセンス検証 → セッション鍵発行
  - `GET /v1/payload/latest`: 暗号化 Payload 配布
  - `POST /v1/telemetry`: 使用量収集 (コード送信なし)
- 小規模 VPS 1 台で運用可能 (Hetzner Cloud 等、月額 $10 程度)
- 月次で Payload を再ビルドして配信

---

## 5. 機密性 (秘匿) 要件

### 5.1 脅威モデル

| 脅威 | 対象 | 対策 |
|---|---|---|
| T1: 攻撃者がプロンプトを入手し、検出を回避する攻撃パターンを作成 | プロンプト・スキル | 暗号化 + RAM 復号 + 月次ローテ |
| T2: Payload バイナリの改竄 | Worker イメージ | Cosign 署名 + SLSA Level 3 |
| T3: Nyx 鯖への侵入 | Payload ソース | アクセス制御 + 監査ログ |
| T4: メモリダンプによる復号済 Payload 抽出 | Worker 実行中メモリ | プロセス分離 + (オプション) TEE |
| T5: EF 側からの漏洩 | ライセンス鍵 | ローテ機構 + EF との NDA |

### 5.2 秘匿層

| レイヤー | 実装 |
|---|---|
| 1. **暗号化** | AES-256-GCM、ライセンス鍵派生 |
| 2. **RAM-only 復号** | tmpfs 不使用、`mlock()` で swap 防止 |
| 3. **署名検証** | Cosign + SLSA provenance |
| 4. **月次ローテ** | プロンプトを毎月再生成、漏洩の時限化 |
| 5. **NDA** | EF との法的拘束 |
| 6. **TEE (将来)** | AWS Nitro Enclaves / Intel SGX |

### 5.3 何を守れないか (受け入れるリスク)

- 十分なリソースを持つ攻撃者による active memory inspection (live debugger 接続)
- 出力 (findings) からのプロンプト挙動の部分的逆推論 (十分な試行で可能)
- Anthropic API トラフィックの観察 (EF 側ネットワーク管理者は可能)

これらは **月次ローテ** と **findings の情報量削減 (内部プロパティ ID をハッシュ化)** で影響を限定する。

---

## 6. 機能要件 (Functional Requirements)

### FR-1: 実行モード

- **full mode**: 対象リポジトリ全体を監査 (週次などの定期実行向け)
- **incremental mode**: `diff-base` からの変更ファイルに関連するプロパティのみ評価 (PR ごと、< 10 分)
- **properties_only mode**: 仕様からプロパティ生成のみ (`05` PoC や手動分析前処理)

### FR-2: 入力

- 対象リポジトリ (GitHub Action の checkout 済ディレクトリ)
- 仕様 URL リスト (EIP / markdown / PDF)
- スコープ (glob include/exclude)
- 予算 (USD / 分)
- 深刻度ゲート

### FR-3: 出力

- SARIF v2.1.0 (必須)
- JSON (機械可読)
- Markdown (PR コメント用)
- GitHub Security タブ自動投稿
- PR コメント自動投稿 (インライン対応)

### FR-4: Ethereum 特化

- EIP 標準チェック (ERC-20/721/1155/4337)
- ハードフォーク仕様差分 (Altair/Bellatrix/Deneb/Electra)
- ビーコンチェーン特化プロパティ (fork choice / attestation)
- EL クライアント特化 (Rust: reth / Go: geth, prysm)

### FR-5: 決定論・再現性

- モデルバージョンピン (`claude-opus-4-6` 等)
- LLM レスポンスキャッシュ (キー: `hash(spec) + hash(code) + model_id + prompt_version`)
- `replay` モードでキャッシュから再実行可能

### FR-6: コスト制御

- Worker 起動時に USD 上限・時間上限を設定
- 上限到達で即時中断、部分結果を返す
- `BudgetExceeded` を SARIF notification として記録

---

## 7. 非機能要件 (Non-Functional Requirements)

| NFR | 目標 |
|---|---|
| NFR-1: 実行時間 (incremental) | < 10 分 (PR ゲート許容範囲) |
| NFR-2: 実行時間 (full) | < 4 時間 |
| NFR-3: Issue Recall (Sherlock ベンチ) | ≥ 0.3 (現状 0.273) |
| NFR-4: FP Rate (Phase 04 後) | ≤ 20% |
| NFR-5: Nyx 配信鯖の可用性 | 99.5% (障害時は Worker がキャッシュで動作) |
| NFR-6: Worker イメージサイズ | < 500 MB |
| NFR-7: Payload ダウンロード時間 | < 30 秒 |
| NFR-8: SARIF 準拠 | v2.1.0 完全準拠、GitHub UI で正常表示 |

---

## 8. インフラ要件

### 8.1 Nyx 側

| コンポーネント | 技術候補 |
|---|---|
| 配信鯖 | FastAPI on Hetzner Cloud / Fly.io |
| DB (ライセンス・テレメトリ) | SQLite or PostgreSQL |
| Payload ストレージ | S3 互換 (Wasabi / R2) |
| シークレット管理 | HashiCorp Vault / age |
| CDN (Payload 配信) | Cloudflare |
| 監視 | Grafana Cloud free tier |

### 8.2 CI 側 (EF)

| 要件 | 詳細 |
|---|---|
| Runner | GitHub-hosted `ubuntu-latest` or self-hosted |
| Docker | `speca-worker` を docker/OCI で実行 |
| 必要リソース | 2 vCPU / 4 GB RAM 最低 |
| ネットワーク | Anthropic API + Nyx 配信鯖への outbound 許可 |

---

## 9. セキュリティ要件 (EF 側)

- EF は `ANTHROPIC_API_KEY` を自己管理 (Anthropic 直接契約)
- `SPECA_LICENSE_KEY` は EF のセキュリティチームが管理
- Worker コンテナは `--read-only` で起動可能 (書き込みは `/tmp` のみ)
- ネットワークは Anthropic API + Nyx 鯖以外を遮断可能 (Docker `--network` 制約対応)
- テレメトリは opt-out 可能 (`send-telemetry: false`)

---

## 10. マイルストーン

| M | 期間 | 目標 | 検証可能な成果 |
|---|---|---|---|
| **M1** | 3週 | Anthropic SDK 移行 + 外殻 worker スケルトン | 空 SARIF 出力が `ghcr` から動作 |
| **M2** | 2週 | 暗号化 Payload + 軽量ライセンス鯖 | 月次ローテ可能な最小鯖が動作 |
| **M3** | 2週 | `speca-action` v1 + SARIF 完全対応 | テストリポで GitHub Security タブ表示 |
| **M4** | 3週 | Incremental mode + diff 解析 + PR コメント | PR 単位で < 10 分実行達成 |
| **M5** | 3週 | EF リポジトリパイロット (`execution-specs` or `reth`) | 実 PR で監査実行・レポート提出 |
| **M6** | 2週 | Cosign 署名 + SLSA L3 + ドキュメント | 署名検証可能 + EF 向け報告書完成 |

**合計: 15 週 (約 4 ヶ月)**

---

## 11. 成功判定基準

### EF グラント成果としての定義
- [ ] EF 指定リポジトリ (少なくとも 1 つ) で `speca-action` が CI に統合され、PR 単位で動作している
- [ ] Issue Recall ≥ 0.3、FP Rate ≤ 20% を達成
- [ ] GitHub Security タブに SARIF findings が正常表示
- [ ] EF セキュリティチームから秘匿性・運用性について承認を得ている
- [ ] ベンチマーク論文 (RQ1/RQ2a) を arXiv 投稿済み

### ユーザー (EF 開発者) としての成功
- [ ] `uses:` 1 行追加だけで監査が走る
- [ ] PR ごとに自動実行され、開発フローを阻害しない (< 10 分)
- [ ] 誤検知で CI が無駄に失敗しない (FP ≤ 20%)

---

## 12. リスクと緩和策

| リスク | 影響 | 緩和策 |
|---|---|---|
| R1: Claude モデル仕様変更 | 出力フォーマット破綻 | モデルピン + レスポンスキャッシュテスト |
| R2: Anthropic API レートリミット | CI が失敗 | Worker 内リトライ + 段階的バックオフ |
| R3: Nyx 配信鯖の障害 | Worker 起動不可 | キャッシュで最後の Payload を使用 (N 日間) |
| R4: プロンプト漏洩 | 攻撃者による回避 | 月次ローテで影響時限化 |
| R5: EF 側の `ANTHROPIC_API_KEY` 流出 | 金銭被害 | EF 側の責任、ドキュメントで明記 |
| R6: SPECA 出力の過検出 | 開発者信頼失墜 | `fail-on` デフォルトを `high` に限定、段階的引き上げ |

---

## 13. オープン課題 (議論が必要)

1. **EF リポジトリの具体的なパイロット対象** — `execution-specs` と `reth` のどちらを先に？
2. **Payload 配信先** — Nyx 自己ホスト vs. Cloudflare R2 / S3 署名 URL
3. **ライセンス鍵管理** — EF 内で部署ごとに発行？ 単一鍵？
4. **テレメトリ範囲** — 成功/失敗のみ？ findings カテゴリ統計も含める？
5. **月次 Payload ローテ運用** — 誰が毎月リリースするか、ローテ失敗時の手動復旧手順
6. **リソース見積もり** — 15 週のエンジニアリング体制 (何人月か)

---

## 14. 参考情報

- 現行パイプライン: `scripts/orchestrator/`, `prompts/01*-04*.md`
- 秘匿配信の類似事例: Semgrep Pro Rules, CrowdStrike Falcon, Cloudflare WAF
- SARIF 仕様: https://sarifweb.azurewebsites.net/
- GitHub Action ベストプラクティス: https://docs.github.com/en/actions/creating-actions/about-custom-actions
- SLSA: https://slsa.dev/
- Cosign: https://docs.sigstore.dev/cosign/overview/

---

## 15. 次のアクション

1. 本 RFC のレビュー・承認
2. M1 着手: `worker/` ディレクトリ作成 + Anthropic SDK 移行開始
3. `speca-action` リポジトリの新規作成 (または本リポ内 `action/` で開発)
4. Payload 配信鯖用 Hetzner Cloud インスタンス準備
