---
sidebar_position: 3
---

# CLI リファレンス

`speca` の各サブコマンドのリファレンスです。実行時にも `speca <subcommand> --help` で確認できます。

## `speca doctor`

ローカル環境を検証します。

```bash
speca doctor
```

Node.js / Python (`uv`) / Claude Code 認証 / MCP サーバー (`fetch`, `tree_sitter`) を確認し、失敗ごとに具体的な対処コマンドを表示します。

## `speca auth login` · `speca auth status`

Claude API 認証情報を管理します。

```bash
speca auth login          # 対話式: API キー or claude セッション
speca auth status         # 現在の認証ソースを表示
```

認証情報は `~/.config/speca/auth.json` に保存されます。環境変数 `ANTHROPIC_API_KEY` も使えます。

## `speca init`

`outputs/TARGET_INFO.json` と `outputs/BUG_BOUNTY_SCOPE.json` を生成します。これらがパイプライン全体の入力になります。

```bash
speca init
```

フラグ (すべて任意。未指定値は対話で尋ねられる):

| フラグ | 説明 |
|---|---|
| `--project-name <name>` | プロジェクト名 (デフォルト: cwd の basename) |
| `--target-repo <url>` | 対象リポジトリ URL |
| `--target-commit <ref>` | コミット / ブランチ / タグ (デフォルト: HEAD) |
| `--target-language <lang>` | Solidity / Rust / Go / Nim / TypeScript / C / C++ / … |
| `--target-layer <layer>` | consensus / execution / application / library / … |
| `--rubric <mode>` | `default` (ethereum.org rubric) または `custom` |
| `--output-dir <dir>` | 出力ディレクトリ (デフォルト `$SPECA_OUTPUT_DIR` または `./outputs/`) |
| `--force`, `--yes` | 既存ファイルを確認なしで上書き |
| `--non-interactive` | 対話を拒否 — すべての値をフラグで渡す |

JSON スキーマは [設定ファイル](./config-files.md) を参照してください。

## `speca run`

パイプラインを実行します。デフォルトでは TUI ダッシュボードが流れます。

```bash
speca run --target 04 --workers 4
speca run --phase 01a 01b 01e
speca run --phase 03 --force --json
```

フラグ:

| フラグ | 説明 |
|---|---|
| `--phase <id…>` | 1 つ以上のフェーズを ID 指定 (例: `--phase 01a 01b`) |
| `--target <id>` | `<id>` までの依存関係を全て実行 |
| `--workers <N>` | フェーズあたりのワーカー数 (デフォルト 4) |
| `--max-concurrent <N>` | Claude 同時起動数の上限 (デフォルト 8) |
| `--force` | resume 状態を無視して再実行 |
| `--budget <usd>` | コスト上限をオーケストレータに渡す |
| `--output-dir <path>` | 出力ディレクトリ (`SPECA_OUTPUT_DIR` を設定) |
| `--no-tui` | プレーンテキスト出力 (CI 向け) |
| `--json` | NDJSON イベントを stdout に流す |
| `--runtime <name>` | 実行 runtime を選択 (`claude` / `api` / `codex` / `gemini` / `ollama` / `copilot`) |
| `--list-runtimes` | 登録済 runtime の一覧と可用性を表示して終了 |
| `--01a-scope <mode>` | Phase 01a の状態を `all` / `primary` / `primary+1hop` / `<N>` でフィルタ |

resume は自動です。`<phase>_PARTIAL_*.json` に書かれた項目はスキップされます。`--force` で無効化できます。`Ctrl-C` での中断は安全で、再実行で続きから処理されます。

### Runtime 選択

`--runtime` フラグで claude 以外のエージェント実行系に切替可能です。バックエンドの認証 / 環境変数 / 各 runtime の制限事項は [Multi-runtime バックエンド](../operations/multi-runtime.md) に整理しています。

```bash
# 登録済 runtime を一覧 + 可用性チェック
speca run --list-runtimes

# JSON で吐く (CI / speca-cli 連携)
speca run --list-runtimes --json

# OpenRouter 経由で audit
speca run --target 04 --runtime api --workers 4

# 未実装 runtime を指定すると exit 2 で安全停止
speca run --target 04 --runtime copilot   # → exit: 2
```

`--runtime` は `ORCHESTRATOR_RUNNER` 環境変数を上書きします。stub 状態の runtime を指定した場合は、silent fallback で誤った PARTIAL を吐くことなく exit 2 で停止します。

フェーズ ID の意味は [パイプライン概要](../pipeline/overview.md) を参照してください。

## `speca browse`

Phase 04 finding の TUI ビューア。

```bash
speca browse                                    # デフォルト glob
speca browse outputs/04_PARTIAL_*.json
speca browse --severity Critical
speca browse --filter "severity:High AND verdict:CONFIRMED_*"
```

フィルタ DSL:

| トークン | マッチ |
|---|---|
| `severity:Critical` | severity 完全一致 (大文字小文字区別なし) |
| `severity:Critical,High` | カンマ区切り OR |
| `verdict:CONFIRMED_*` | ワイルドカード後方一致 |
| `prop:PROP-6a4*` | `property_id` のワイルドカード一致 |
| `repo:lighthouse` | ソースファイルパスへの部分一致 |
| `text:reentrancy` | summary / proof / attack / notes の部分一致 |
| `... AND ...`, `... OR ...`, `NOT ...`, 括弧 | 真偽値合成 |

TUI キー: `↑/↓` (または `j/k`) で移動、`Enter` で詳細展開、`c` でコード覗き、`f` でフィルタ編集、`/` でクイックテキスト検索、`s` でソート切替、`r` で再読込、`q` で終了。

`--no-tui` / `--json` ではマッチした findings を stdout に出力します。

## `speca ask`

1 つの finding のコンテキストを事前にロードした Claude Code セッションを開きます。

```bash
speca ask                                          # 最初の finding を対話的に選択
speca ask PROP-abc-001 --from outputs/04_PARTIAL_*.json
speca ask --session 9f1c2e0a-...                   # 既存セッションを再開
speca ask --no-tui --from finding.json --max-context 10000
```

「証明のどのステップが失敗しているか」「最小修正パッチを示せ」「これは本当の脆弱性か FP か」といった質問を投げるのに使います。

## `speca version`

CLI バージョン (および対応するパイプラインスキーマバージョン) を表示します。

## 終了コード

| コード | 意味 |
|---|---|
| 0 | 成功 |
| 1 | ユーザー可視のエラー (CLI が対処ヒントを表示) |
| 2 | 呼び出し誤り (未知のフラグ・必須引数欠落) |
| 64 | 予算超過 — `--budget` に到達 |
| 65 | サーキットブレーカー作動 — 連続失敗が閾値超過 |

64 と 65 は CI スクリプトで捕捉できるよう設計されています。暴走したランで予算を食いつぶすのを防げます。
