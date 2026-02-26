# 引き継ぎ資料 2 — Critical セキュリティ脆弱性修正セッション

> 次回セッション開始時にこのファイルを読んで状況を把握してください。
> 最終更新: 2026-02-23

---

## 1. 今回のセッションで完了したこと

### Critical セキュリティ脆弱性 4件の修正

`docs/hiro/kijaku.md` に記載された **Critical 4件** (SEC-C01〜C04) をすべて修正済み。

| ID | 脆弱性 | ファイル | 修正内容 |
|---|---|---|---|
| SEC-C01 | コマンドインジェクション (`run_command`) | `benchmarks/runners/base_runner.py` | `shell=True` 時に `shlex.quote()` で全パラメータをエスケープ |
| SEC-C02 | パストラバーサル (LLM出力パス) | `scripts/orchestrator/base.py` | `_is_safe_output_path()` ヘルパー追加、`outputs/` 外へのアクセスをブロック |
| SEC-C03 | スクリプトインジェクション (GitHub Actions) | `.github/workflows/openhands-resolver.yml` | `${{ }}` 展開を `context.payload` 経由に変更 |
| SEC-C04 | コマンドインジェクション (`resolve_version`) | `benchmarks/runners/base_runner.py` | `shlex.split()` + `shell=False` に変更 |

### 追加したテスト

| テストファイル | 件数 | 内容 |
|---|---|---|
| `tests/test_sec_c01_c04_command_injection.py` | 8件 | シェルエスケープ検証、`shell=False` 検証 |
| `tests/test_sec_c02_path_traversal.py` | 6件 | パストラバーサルガードの正常/異常パス検証 |
| `tests/test_schemas_and_config.py` (修正) | 2件修正 | 一時ファイルを `outputs/` 内に作成するよう変更 |

### テスト結果

- **230 テスト全パス** (5.00s)
- リグレッションなし

---

## 2. ブランチ・PR 状態

| 項目 | 値 |
|------|-----|
| **作業ブランチ** | `claude/confident-lewin` |
| **ベースブランチ** | `master` |
| **コミット** | `384269ca` — `fix: Critical セキュリティ脆弱性 4件を修正 (SEC-C01〜C04)` |
| **PR** | 未作成（下記のPR文面を使って手動作成） |

---

## 3. 次回やるべきこと — 残りの脆弱性修正

`docs/hiro/kijaku.md` の残り **66件** の修正が必要。優先度順:

### P0 — 即時対応（完了済み）

- ~~SEC-C01/C04: コマンドインジェクション~~ 完了
- ~~SEC-C02: パストラバーサル~~ 完了
- ~~SEC-C03: スクリプトインジェクション~~ 完了

### P1 — 短期対応（次回推奨）

| ID | 概要 | ファイル |
|---|---|---|
| SEC-H01 | Gitトークン漏洩（8ワークフロー） | `.github/workflows/*.yml` |
| SEC-H02 | TOCTOU レース（MCP設定ファイル） | `scripts/orchestrator/runner.py` |
| SEC-H03 | レースコンディション（PARTIAL読み取り） | `scripts/orchestrator/resume.py`, `collector.py` |
| SEC-H04 | sweagent 未ピン留め | `pyproject.toml` |
| SEC-H05 | ワークフロー権限の過剰付与 | `.github/workflows/*.yml` |
| BUG-CI01 | Heredoc で BUG_BOUNTY_SCOPE.json 不正JSON | `01e-properties.yml` |
| BUG-CI02 | git user.name/email 未設定 | `benchmark-rq1-sherlock-eval.yml` |
| BUG-CI03 | upload-artifact@v6 → @v4 | `openhands-resolver.yml` |
| BUG-CI04 | ブランチ未プッシュ | `benchmark-rq2-01-setup.yml` |
| BUG-ORC01 | `sys.exit()` → カスタム例外 | `scripts/orchestrator/base.py` |
| BUG-ORC03 | 正規表現 大文字/小文字不一致 | `scripts/orchestrator/resume.py` |
| BUG-SCH01/02 | スキーマ/enum と Phase 03 出力の不一致 | `scripts/orchestrator/schemas.py` |

### P2 — 中期対応

- SEC-M01〜M06: Medium セキュリティ脆弱性 6件
- BUG-ORC02/04/05: オーケストレーターロジックバグ
- BUG-BEN01〜08: ベンチマーク/評価のバグ
- BUG-SCH03〜07: スキーマ整合性 + テスト修正

### アプローチ推奨

- **High 5件 (SEC-H01〜H05)** は影響範囲が広いため、まとめて1セッションで対応するのが効率的
- SEC-H01（Gitトークン漏洩）は 8 ワークフローの一括置換なのでエージェント並列実行が有効
- SEC-H02/H03（レースコンディション）はアトミック書き込み実装のため一緒に対応推奨
- BUG-ORC/SCH 系は相互依存があるためスキーマ修正を先に行うこと

---

## 4. 技術的な注意点

### SEC-C02 のパスバリデーション

- `_is_safe_output_path()` は `Path("outputs").resolve()` をベースにしている
- CWD が変わると挙動が変わるため、テストは CWD がリポジトリルートである前提
- 既存テスト (`test_schemas_and_config.py`) で一時ファイルを `outputs/` 内に作成するよう変更した点に注意

### SEC-C01 の shlex.quote()

- `use_shell=True` 時のみエスケープ適用。`use_shell=False` 時は従来通り `shlex.split()` でトークン化
- テンプレート内のプレースホルダーがクォートされた値に置換されるため、テンプレート自体にクォートを含めないこと

---

## 5. よく使うコマンド

```bash
# テスト実行（全フェーズ前に必須）
uv run python3 -m pytest tests/ -v --tb=short

# セキュリティ関連テストのみ
uv run python3 -m pytest tests/test_sec_*.py -v

# 変更差分の確認
git diff master..HEAD --stat
```
