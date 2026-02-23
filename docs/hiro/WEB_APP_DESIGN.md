# SPECA Web アプリケーション設計考察

> 作成日: 2026-02-23

---

## 目次

1. [動機](#1-動機と学会貢献への位置づけ)
2. [Web アプリが解決する課題](#2-web-アプリが解決する課題)
3. [アーキテクチャ選択肢の比較](#3-アーキテクチャ選択肢の比較)
4. [機能設計](#4-機能設計)
5. [データフローと既存パイプラインへの影響](#5-データフローと既存パイプラインへの影響)
6. [技術スタックの推奨](#6-技術スタックの推奨)
7. [実装フェーズ計画](#7-実装フェーズ計画)
8. [リスクと緩和策](#9-リスクと緩和策)
9.  [既存コードへの影響分析](#10-既存コードへの影響分析)

---

## 1. 動機と

### 1.1 なぜ Web アプリが必要か

SPECA は 6 フェーズの自動監査パイプラインだが、現状の出力は JSON ファイル群と Markdown レポートのみ。

| 不足点 | 影響 |
|---|---|
| **対話的な結果探索** | 査読者が PARTIAL JSON を手動で開いて確認する必要がある |
| **形式的監査の過程の可視化** | 3 フェーズ監査（抽象解釈→記号実行→不変条件証明）の推論過程が JSON に埋もれている |
| **再現性の実証** | パイプラインの実行自体が Claude Code CLI に依存し、デモが困難 |
| **ベンチマーク結果の比較** | RQ1/RQ2 の結果が静的 PNG + JSON で、動的フィルタリングができない |
| **プログラムグラフの閲覧** | Mermaid `.mmd` ファイルがレンダリングされていない |

### 1.2  Web アプリの役割

```
論文本体 ←→ Artifact（再現性評価）←→ Web デモ（対話的探索）
```

- **トップ会場 (S&P, USENIX, CCS)**: Artifact Evaluation (AE) が標準化。Web デモは「Available」「Functional」「Reproduced」バッジ取得を強力に支援
- **SE 会場 (ASE, ISSTA, FSE)**: ツール論文 (Tool Paper) としての投稿では対話的デモが事実上必須

**結論**: Web アプリは論文の「評価」セクションの説得力を劇的に高める。

---



---

## 3. アーキテクチャ選択肢の比較

### 3.1 選択肢

| 選択肢 | 技術 | 長所 | 短所 |
|---|---|---|---|
| **A. 静的サイト** | Next.js + 静的 JSON | デプロイ簡単、GitHub Pages 対応 | 動的フィルタリングに限界 |
| **B. フルスタック** | Next.js + FastAPI | 柔軟、リアルタイム対応可 | インフラ管理が必要 |
| **C. Streamlit** | Streamlit | Python のみ、既存コードと親和性高い | UI カスタマイズ性が低い、学会デモとしてやや安っぽい |
| **D. Jupyter Book** | Jupyter + MyST | 論文と統合しやすい | 対話性が低い |
| **E. 静的サイト (軽量)** | Astro/Vite + Preact | 極軽量、JSON 直読み | SPA の複雑性あり |

### 3.2 推奨: **選択肢 A（静的サイト + JSON）**

**理由**:

1. **デプロイの容易さ**: GitHub Pages / Vercel で無料ホスティング。査読者がワンクリックでアクセス可能
2. **バックエンド不要**: 既存の JSON 出力をそのまま `public/data/` に配置するだけ
3. **既存パイプラインへの影響ゼロ**: パイプラインは JSON を出力するだけで変更不要
4. **Artifact としての配布性**: `npm run build` → 静的ファイル一式を ZIP で提出可能
5. **学会デモとしての品質**: Next.js の SSG (Static Site Generation) はプロフェッショナルな見た目を提供


### 3.3 ディレクトリ構成案

```
security-agent/
├── web/                          # 新規ディレクトリ（既存に影響なし）
│   ├── package.json
│   ├── next.config.js
│   ├── tsconfig.json
│   ├── public/
│   │   └── data/                 # パイプライン出力の JSON をコピー
│   │       ├── rq2/
│   │       │   ├── evaluation_summary.json
│   │       │   ├── metrics.json
│   │       │   └── figures/
│   │       ├── rq1/
│   │       │   ├── evaluation_summary.json
│   │       │   ├── report.md
│   │       │   └── collection_summary.json
│   │       └── audit/
│   │           ├── 03_AUDITMAP_PARTIAL_*.json
│   │           └── 04_REVIEW_PARTIAL_*.json
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx          # ランディング（概要）
│   │   │   ├── rq2/page.tsx      # RQ2 ダッシュボード
│   │   │   ├── rq1/page.tsx      # RQ1 エクスプローラー
│   │   │   ├── audit/page.tsx    # 監査トレイル閲覧
│   │   │   └── graphs/page.tsx   # プログラムグラフ
│   │   ├── components/
│   │   │   ├── charts/           # Recharts / D3 ベースのチャート
│   │   │   ├── tables/           # TanStack Table ベースのデータテーブル
│   │   │   ├── audit-trail/      # 3 フェーズ展開表示
│   │   │   └── code-viewer/      # シンタックスハイライト付きコードビューア
│   │   └── lib/
│   │       ├── types.ts          # schemas.py から自動生成
│   │       └── data-loader.ts    # JSON ローダー
│   └── scripts/
│       └── sync-data.sh          # outputs/ → web/public/data/ のコピースクリプト
├── scripts/orchestrator/         # 変更なし
├── benchmarks/                   # 変更なし
└── outputs/                      # 変更なし
```

---

## 4. 機能設計

### 4.1 RQ2 ベンチマークダッシュボード (`/rq2`)

**データソース**: `benchmarks/results/rq2/evaluation_summary.json`, `metrics.json`

```
┌──────────────────────────────────────────────────────┐
│  RQ2: Tool Comparison Dashboard                       │
│                                                       │
│  ┌──────────────────┐  ┌──────────────────────────┐  │
│  │ [棒グラフ]        │  │ [レーダーチャート]         │  │
│  │ Precision/Recall  │  │ 各指標の多角的比較         │  │
│  │ /F1 ツール別比較  │  │ semgrep vs codeql vs ...  │  │
│  └──────────────────┘  └──────────────────────────┘  │
│                                                       │
│  ┌────────────────────────────────────────────────┐   │
│  │ [テーブル] 詳細メトリクス                         │   │
│  │ Tool | Prec | Rec | F1 | TP | FP | TN | FN    │   │
│  │ ─────┼──────┼─────┼────┼────┼────┼────┼─────  │   │
│  │ semg | 0.00 | ... | .. | .. | .. | .. | ...    │   │
│  └────────────────────────────────────────────────┘   │
│                                                       │
│  ┌────────────────────────────────────────────────┐   │
│  │ [ヒートマップ] CWE カバレッジ                     │   │
│  │ CWE-787 | CWE-125 | CWE-416 | ...             │   │
│  │ tool 別 recall をセルの色で表現                   │   │
│  └────────────────────────────────────────────────┘   │
│                                                       │
│  ┌────────────────────────────────────────────────┐   │
│  │ [カード] 統計検定                                │   │
│  │ McNemar p-value | Cliff's delta | Bootstrap CI │   │
│  └────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────┘
```

**インタラクション**:
- データセット切替（PrimeVul / CVEfixes / Vul4J）
- ツール選択フィルタ
- CWE カテゴリフィルタ
- Bootstrap CI の信頼区間スライダー

### 4.2 RQ1 監査エクスプローラー (`/rq1`)

**データソース**: `benchmarks/results/rq1/sherlock_ethereum_audit_contest/`

```
┌──────────────────────────────────────────────────────┐
│  RQ1: Ethereum Client Audit Results                   │
│                                                       │
│  [クライアント選択タブ]                                │
│  Lighthouse | Prysm | Nimbus | Lodestar | Teku | ... │
│                                                       │
│  ┌────────────────────────────────────────────────┐   │
│  │ [サマリーカード]                                 │   │
│  │ Findings: 54 | Matched: 51 | Issue Recall: 53% │   │
│  │ Runtime: 25m | Tokens: 9.8M                     │   │
│  └────────────────────────────────────────────────┘   │
│                                                       │
│  ┌────────────────────────────────────────────────┐   │
│  │ [テーブル] マッチした Issues                      │   │
│  │ Issue # | Severity | Title | Agent Finding      │   │
│  │ #40     | High     | Proposer calc | CHECK-...  │   │
│  └────────────────────────────────────────────────┘   │
│                                                       │
│  ┌────────────────────────────────────────────────┐   │
│  │ [テーブル] 未マッチ Issues (false negatives)     │   │
│  │ Issue # | Severity | 未マッチ理由               │   │
│  └────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────┘
```

### 4.3 監査トレイルビューア (`/audit`)

**データソース**: `outputs/03_AUDITMAP_PARTIAL_*.json`, `outputs/04_REVIEW_PARTIAL_*.json`

```
┌──────────────────────────────────────────────────────┐
│  Audit Trail Viewer                                   │
│                                                       │
│  [検索バー] property_id / CWE / severity / keyword    │
│  [フィルタ] Classification: ●Vulnerable ●Safe ●Inc.  │
│             Severity: ●Critical ●High ●Medium ●Low   │
│                                                       │
│  ┌────────────────────────────────────────────────┐   │
│  │ PROP-W0-FULUFC-PRECOND-008                     │   │
│  │ Severity: Medium | Classification: vulnerable  │   │
│  │ Bug Class: post-boundary-validation             │   │
│  │                                                 │   │
│  │ ▼ Phase 1: Abstract Interpretation              │   │
│  │   ┌────────────────────────────────────────┐    │   │
│  │   │ Graph element implemented in            │    │   │
│  │   │ beacon_node/lighthouse_network/src/...  │    │   │
│  │   │ State anomalies: [cache inconsistency]  │    │   │
│  │   └────────────────────────────────────────┘    │   │
│  │                                                 │   │
│  │ ▼ Phase 2: Symbolic Execution                   │   │
│  │   ┌────────────────────────────────────────┐    │   │
│  │   │ Counterexample found: true              │    │   │
│  │   │ Attack path: P2P gossip → ...           │    │   │
│  │   │ Entry points: ["P2P"]                   │    │   │
│  │   └────────────────────────────────────────┘    │   │
│  │                                                 │   │
│  │ ▼ Phase 3: Invariant Proving                    │   │
│  │   ┌────────────────────────────────────────┐    │   │
│  │   │ Proof successful: false                 │    │   │
│  │   │ Guard analysis: bounds check missing... │    │   │
│  │   └────────────────────────────────────────┘    │   │
│  │                                                 │   │
│  │ ▼ Code                                          │   │
│  │   ┌────────────────────────────────────────┐    │   │
│  │   │ beacon_node/.../rpc/methods.rs:570-608 │    │   │
│  │   │ pub fn validate_request(...) {          │    │   │
│  │   │   // highlighted code                   │    │   │
│  │   │ }                                       │    │   │
│  │   └────────────────────────────────────────┘    │   │
│  └────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────┘
```

**コアインタラクション**:
- 3 フェーズのアコーディオン展開（デフォルトは折りたたみ）
- コードスニペットのシンタックスハイライト（Rust, Go, TypeScript, Java）
- Severity / Classification / Bug Class によるフィルタリング
- JSON 生データのトグル表示

### 4.4 プログラムグラフビューア (`/graphs`)

**データソース**: `outputs/graphs/{spec_id}/*.mmd`

- Mermaid.js でサーバーサイドレンダリング不要のグラフ表示
- グラフ要素（ノード/エッジ）のクリックで関連プロパティにジャンプ
- YAML フロントマターの表示（invariant ブロック含む）

---

## 5. データフローと既存パイプラインへの影響

### 5.1 データ同期方式

```
[パイプライン実行]              [Web アプリ]

outputs/ ──────────────→ web/public/data/
                 sync-data.sh
benchmarks/results/ ───→ web/public/data/
                 sync-data.sh
```

**`web/scripts/sync-data.sh`** (新規):

```bash
#!/usr/bin/env bash
# パイプライン出力 → Web アプリの静的データにコピー
# パイプライン側は一切変更しない
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DATA_DIR="${ROOT}/web/public/data"
mkdir -p "${DATA_DIR}"/{rq1,rq2,audit,graphs}

# RQ2 結果
cp -r "${ROOT}/benchmarks/results/rq2/"*.json "${DATA_DIR}/rq2/" 2>/dev/null || true
cp -r "${ROOT}/benchmarks/results/rq2/figures" "${DATA_DIR}/rq2/" 2>/dev/null || true

# RQ1 結果
cp -r "${ROOT}/benchmarks/results/rq1/sherlock_ethereum_audit_contest/"*.json "${DATA_DIR}/rq1/" 2>/dev/null || true

# 監査結果
cp "${ROOT}/outputs/03_AUDITMAP_PARTIAL_"*.json "${DATA_DIR}/audit/" 2>/dev/null || true
cp "${ROOT}/outputs/04_REVIEW_PARTIAL_"*.json "${DATA_DIR}/audit/" 2>/dev/null || true

# プログラムグラフ
cp -r "${ROOT}/outputs/graphs/" "${DATA_DIR}/graphs/" 2>/dev/null || true
```

### 5.2 既存パイプラインへの影響: **ゼロ**

| 既存コンポーネント | 変更の必要性 |
|---|---|
| `scripts/orchestrator/` | なし。JSON 出力フォーマットは不変 |
| `scripts/run_phase.py` | なし |
| `benchmarks/rq2/evaluate.py` | なし。出力フォーマットは不変 |
| `benchmarks/rq2/generate_report.py` | なし |
| `.github/workflows/` | `sync-data.sh` + `deploy` ステップを追加するのみ |
| `tests/` | なし。Web は独立したテストスイート |
| `prompts/` | なし |
| `.claude/skills/` | なし |

**設計原則**: Web アプリはパイプラインの「読み取り専用ビュー」であり、パイプラインのコードやデータフローには一切手を加えない。

### 5.3 型定義の同期

`scripts/orchestrator/schemas.py` の Pydantic モデルから TypeScript 型を自動生成する:

```bash
# pydantic-to-typescript で自動生成
pip install pydantic-to-ts
pydantic2ts --module scripts.orchestrator.schemas --output web/src/lib/types.ts
```

これにより、フロントエンドの型定義とバックエンドのスキーマが常に同期する。

---

## 6. 技術スタックの推奨

### 6.1 フロントエンド

| カテゴリ | 推奨 | 理由 |
|---|---|---|
| フレームワーク | **Next.js 14+ (App Router, SSG)** | 静的サイト生成、React エコシステム、Vercel デプロイ |
| 言語 | **TypeScript** | 型安全、Pydantic からの型生成と親和性高い |
| UI | **shadcn/ui + Tailwind CSS** | プロフェッショナルな外観、カスタマイズ性高い |
| チャート | **Recharts** (棒/レーダー) + **D3.js** (ヒートマップ) | React 統合、学術的な可視化に十分 |
| テーブル | **TanStack Table** | ソート、フィルタ、ページネーション |
| コードビューア | **Shiki** (シンタックスハイライト) | VS Code と同じハイライトエンジン |
| グラフ | **Mermaid.js** | .mmd ファイルの直接レンダリング |

### 6.2 ビルド & デプロイ

| カテゴリ | 推奨 | 理由 |
|---|---|---|
| ビルド | `next build && next export` | 静的 HTML/CSS/JS を出力 |
| ホスティング | **Vercel** (第一候補) / **GitHub Pages** (フォールバック) | 無料、カスタムドメイン、自動デプロイ |
| CI | GitHub Actions | `sync-data.sh` → `npm run build` → デプロイ |

### 6.3 開発環境

```bash
# web/ ディレクトリでの開発
cd web
npm install
npm run dev        # http://localhost:3000
npm run build      # 静的サイト生成
npm run type-check # TypeScript 型チェック
```

---

## 7. 実装フェーズ計画

### Phase 1: 基盤 + RQ2 ダッシュボード（1-2 週間）

```
目標: 査読者が最も関心を持つ RQ2 結果を対話的に探索できるようにする
```

- [ ] Next.js プロジェクト初期化（`web/` ディレクトリ）
- [ ] `sync-data.sh` スクリプト作成
- [ ] `schemas.py` → TypeScript 型自動生成
- [ ] ランディングページ（プロジェクト概要 + パイプラインフロー図）
- [ ] RQ2 ダッシュボード
  - [ ] ツール比較棒グラフ（Precision / Recall / F1）
  - [ ] 詳細メトリクステーブル
  - [ ] CWE カバレッジヒートマップ
  - [ ] 統計検定結果カード（McNemar, Cliff's delta, Bootstrap CI）
- [ ] Vercel デプロイ設定

### Phase 2: RQ1 エクスプローラー（1 週間）

```
目標: Ethereum クライアント別の監査結果を対話的に探索
```

- [ ] クライアント選択タブ（6 クライアント）
- [ ] サマリーカード（Findings, Matched, Issue Recall, Runtime, Tokens）
- [ ] マッチ / アンマッチ Issue テーブル
- [ ] 実行メタデータ（トークン消費、ターン数）の可視化

### Phase 3: 監査トレイルビューア（1-2 週間）

```
目標: 3 フェーズ形式的監査の推論過程を対話的に閲覧
```

- [ ] 監査アイテム一覧（検索、フィルタ）
- [ ] 3 フェーズアコーディオン展開
- [ ] コードスニペットビューア（Shiki）
- [ ] Severity / Classification / Bug Class フィルタ
- [ ] Phase 04 レビュー結果の統合表示

### Phase 4: プログラムグラフ + 仕上げ（1 週間）

```
目標: 形式的プログラムグラフの可視化と全体の統合
```

- [ ] Mermaid.js によるグラフレンダリング
- [ ] グラフ → プロパティ → 監査トレイルのナビゲーション
- [ ] レスポンシブデザイン
- [ ] OGP メタタグ（SNS 共有対応）
- [ ] パフォーマンス最適化（大量 JSON の遅延読み込み）

**合計見積もり: 4-6 週間**


## 10. 既存コードへの影響分析

### 10.1 変更が必要なファイル

| ファイル | 変更内容 | 影響度 |
|---|---|---|
| `.gitignore` | `web/node_modules/`, `web/.next/`, `web/out/` を追加 | 最小 |
| `pyproject.toml` | `pydantic-to-ts` を dev-dependencies に追加（任意） | 最小 |
| `.github/workflows/` | デプロイ用ワークフロー新規追加 | 新規のみ |

### 10.2 変更が不要なファイル（既存コードは一切触らない）

- `scripts/orchestrator/` — パイプラインロジック
- `scripts/run_phase.py` — 実行エントリポイント
- `prompts/` — ワーカープロンプト
- `.claude/skills/` — スキル定義
- `benchmarks/` — ベンチマークパイプライン
- `tests/` — テストスイート
- `outputs/` — パイプライン出力

### 10.3 CI パイプラインへの追加

```yaml
# .github/workflows/deploy-web.yml (新規)
name: Deploy Web Dashboard
on:
  push:
    branches: [master]
    paths:
      - 'web/**'
      - 'benchmarks/results/**'
      - 'outputs/**'
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Sync data
        run: bash web/scripts/sync-data.sh
      - name: Build
        working-directory: web
        run: npm ci && npm run build
      - name: Deploy to Vercel
        uses: amondnet/vercel-action@v25
        with:
          vercel-token: ${{ secrets.VERCEL_TOKEN }}
          working-directory: web
```

### 10.4 monorepo 管理

`web/` は独立した Node.js プロジェクトとして管理。Python パイプラインとは完全に分離:

```
security-agent/          ← Python (uv)
└── web/                 ← Node.js (npm)
    ├── package.json
    └── ...
```

`uv sync` は `web/` を無視し、`npm install` は `security-agent/` の Python コードを無視する。依存関係の衝突は発生しない。

---

## まとめ

| 項目 | 推奨 |
|---|---|
| **アーキテクチャ** | Next.js SSG (静的サイト生成) |
| **既存への影響** | ゼロ（`web/` ディレクトリで完全分離） |
| **MVP スコープ** | RQ2 ダッシュボード + RQ1 エクスプローラー + 監査トレイルビューア |
| **開発期間** | 4-6 週間（MVP 2-3 週間） |
| **デプロイ** | Vercel / GitHub Pages |


**最重要ポイント**: Web アプリはパイプラインの「読み取り専用ウィンドウ」であり、既存のコードベースには一切手を加えない。データの同期は `sync-data.sh` によるファイルコピーのみで実現する。
