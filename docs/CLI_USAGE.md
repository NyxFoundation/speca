# speca-cli 使い方ガイド

## 前提条件

以下がインストールされていること：

- **Node.js** >= 20
- **uv** (Python パッケージマネージャ)
- **git**
- **claude** (Claude Code CLI) — `npm install -g @anthropic-ai/claude-code`

## セットアップ

```bash
# リポジトリをクローン
git clone https://github.com/NyxFoundation/speca.git
cd speca

# CLI の依存関係をインストール & ビルド
cd cli
npm install
npm run build
cd ..
```

ビルド後は `node cli/dist/cli.js` で実行できる。
エイリアスを張ると便利：

```bash
alias speca="node $(pwd)/cli/dist/cli.js"
```

## コマンド一覧

| コマンド | 説明 |
|---|---|
| `speca doctor` | 環境チェック (Node, uv, git, claude, auth) |
| `speca init` | プロジェクト初期設定ウィザード |
| `speca auth login` | Anthropic OAuth ログイン |
| `speca auth status` | 認証情報の確認 |
| `speca run` | パイプライン実行 + ライブダッシュボード |
| `speca browse` | Finding ブラウザ（対話型テーブル） |
| `speca ask` | Claude に Finding について質問 |
| `speca version` | バージョン表示 |
| `speca help` | ヘルプ表示 |

## 基本的な使い方

### 1. 環境チェック

```bash
speca doctor
```

すべて `[OK]` になっていれば OK。`[WARN] auth` は認証前なら正常。

### 2. 認証

Claude Code サブスクリプション（Pro/Max）がある場合：

```bash
speca auth login
```

ブラウザで Anthropic にログインし、表示されたコードをターミナルに貼り付ける。

API キーを使う場合：

```bash
speca auth login --api-key sk-ant-api03-...
```

認証状態の確認：

```bash
speca auth status
```

### 3. プロジェクト初期設定

```bash
speca init
```

対話式ウィザードが起動し、以下を聞かれる：

1. **ターゲットリポジトリ** — GitHub URL or `owner/repo`
2. **ブランチ/コミット** — ローカルクローンがあれば自動検出
3. **バグバウンティ情報** — プログラム名、URL、スコープ

完了すると `outputs/TARGET_INFO.json` と `outputs/BUG_BOUNTY_SCOPE.json` が生成される。

### 4. パイプライン実行

```bash
# 特定のフェーズを実行
speca run --phase 01a

# 複数フェーズ
speca run --phase 01a 01b 01e

# ターゲットフェーズまで依存解決して実行
speca run --target 03

# ワーカー数指定
speca run --target 04 --workers 4

# 強制再実行（レジューム無視）
speca run --phase 03 --force
```

ライブダッシュボードが表示され、各フェーズの進捗・ログ・バジェットがリアルタイムで確認できる。
`q` で停止。

### 5. Finding ブラウザ

```bash
speca browse
```

`outputs/` ディレクトリの Phase 04（なければ Phase 03）の PARTIAL ファイルを読み込み、テーブル表示する。

**操作:**

| キー | 操作 |
|---|---|
| `j` / `↓` | 次の Finding へ |
| `k` / `↑` | 前の Finding へ |
| `Enter` | 詳細表示 |
| `/` | フィルタ入力 |
| `Esc` | 詳細/フィルタから戻る |
| `q` | 終了 |

**フィルタ構文:**

```
severity:Critical                  # 重大度でフィルタ
verdict:Confirmed                  # 判定でフィルタ
prop:FN-001                        # プロパティIDでフィルタ
severity:High overflow             # 複合フィルタ（AND結合）
```

### 6. Claude に質問

```bash
speca ask
```

Finding のコンテキストを自動で Claude に渡し、チャット形式で質問できる。
セッションは `.speca/session.json` に保存され、次回 `--resume` で続きから会話可能。

## フェーズ一覧

| Phase | 内容 |
|---|---|
| `01a` | 仕様ディスカバリ |
| `01b` | サブグラフ抽出 |
| `01e` | プロパティ生成 |
| `02c` | コード事前解決 |
| `03` | 監査マップ（形式証明ベース） |
| `04` | レビュー（3ゲート FP フィルタ） |

依存関係: `01a → 01b → 01e → 02c → 03 → 04`

## トラブルシューティング

### `speca doctor` で `[FAIL]` が出る

- **node**: Node.js 20+ をインストール → https://nodejs.org/
- **uv**: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **git**: https://git-scm.com/downloads
- **claude**: `npm install -g @anthropic-ai/claude-code`

### `speca auth login` で認証できない

- ブラウザで claude.ai にログインできるか確認
- コードのペースト形式: 完全な callback URL, `code#state`, `code=...&state=...` のいずれか
- フォールバック: `speca auth login --api-key <key>` で API キーを使う

### `speca browse` で何も表示されない

- `outputs/` に `04_PARTIAL_*.json` または `03_PARTIAL_*.json` があるか確認
- まだパイプラインを実行していなければ `speca run --phase 01a` から始める

### `speca run` でエラー

- `speca doctor` で環境を確認
- `outputs/TARGET_INFO.json` があるか確認（なければ `speca init` を実行）
- Phase 01e は `outputs/BUG_BOUNTY_SCOPE.json` が必須
