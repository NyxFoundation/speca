# Pull Request: bug/fix-1

## タイトル

**fix: kijaku.md記載の全66件のバグ修正（ORC/SCH/CI/BEN全カテゴリ完了）**

## 概要

`docs/hiro/kijaku.md` に記載されたバグ84件のうち、SEC-C01〜C04（セキュリティ脆弱性4件、別PR対応済み）と重複14件を除く **全66件** を修正しました。4並列エージェントによる同時修正で全236テストがパスしています。

## 変更内容

---

### Orchestrator（20件）

#### 第1回修正（5件）

| Bug ID | 重要度 | 内容 | 対象ファイル |
|--------|--------|------|-------------|
| BUG-ORC01 | High | `sys.exit()` を `PhaseAbortError` 例外に置換。プロセス強制終了を防ぎ、正常な例外処理フローを実現 | `scripts/orchestrator/base.py`, `scripts/orchestrator/__init__.py`, `scripts/run_phase.py` |
| BUG-ORC03 | High | `resume.py` の正規表現が大文字のみマッチし、小文字ディレクトリ名（`batch_w1b2_...`）を見逃す問題を修正。`re.IGNORECASE` + `.upper()` 追加 | `scripts/orchestrator/resume.py` |
| BUG-ORC05 | Medium | Phase04 `load_items` でリスト結合時に `property_id` 重複が発生する問題を dict ベースの重複排除に修正 | `scripts/orchestrator/base.py` |
| BUG-ORC12 | Low | 存在しない phase `"02"` の dead code ブロックを削除 | `scripts/orchestrator/runner.py` |

#### 第2回修正（15件）

| Bug ID | 重要度 | 内容 | 対象ファイル |
|--------|--------|------|-------------|
| BUG-ORC02 | High | early-exit時の部分結果が `save_partial()` されず消失する問題を修正 | `scripts/orchestrator/base.py` |
| BUG-ORC04 | High | `--force` が上流phaseまで削除する問題を対象phaseのみに限定 | `scripts/run_phase.py` |
| BUG-ORC06 | Medium | `_enrich_with_subgraph_context()` で `subgraph_file` 欠損時に `file_path` フォールバック追加 | `scripts/orchestrator/base.py` |
| BUG-ORC07 | High | `asyncio.Semaphore`/`asyncio.Lock` がイベントループ外で生成される問題を遅延初期化に修正 | `scripts/orchestrator/base.py` |
| BUG-ORC08 | Medium | batch_indexが1始まり（pre-increment）だった問題を0始まり（post-increment）に修正 | `scripts/orchestrator/base.py` |
| BUG-ORC09 | Medium | watchdog `LogWatcher` のファイル読み取りをテキストからバイナリモードに変更（一貫したオフセット追跡） | `scripts/orchestrator/watchdog.py` |
| BUG-ORC10 | Low | プロンプト先頭の意図的な空白を削除する `lstrip()` を除去 | `scripts/orchestrator/runner.py` |
| BUG-ORC11 | Medium | cleanup dry-runでログファイルが二重カウントされる問題を `counted_logs` setで防止 | `scripts/orchestrator/resume.py` |
| BUG-ORC13 | Medium | watchdogループ終了後に未読データが残る問題を最終読み取り追加で修正 | `scripts/orchestrator/watchdog.py` |
| BUG-ORC14 | Low | 全バッチが同じデバッグディレクトリを使用する問題をバッチ固有パスに分離 | `scripts/orchestrator/runner.py` |
| BUG-ORC15 | Medium | `num_turns` がメッセージ数を返していた問題をターン数（÷2）に修正 | `scripts/orchestrator/watchdog.py` |
| BUG-ORC16 | Low | `save_partial()` にオプショナルな `timestamp` パラメータ追加 | `scripts/orchestrator/collector.py` |
| BUG-ORC17 | Medium | 例外メッセージに `W{id}B{idx}:` プレフィックス追加でデバッグ容易化 | `scripts/orchestrator/base.py` |
| BUG-ORC18 | Low | 到達不能な `KeyError` ハンドラ（L724, L933）を削除 | `scripts/orchestrator/runner.py` |
| BUG-ORC19 | Low | スペースを含む引数のクォート処理 `_quote()` ヘルパー追加 | `scripts/orchestrator/runner.py` |

---

### Schema/Config（13件）

#### 第1回修正（4件）

| Bug ID | 重要度 | 内容 | 対象ファイル |
|--------|--------|------|-------------|
| BUG-SCH01 | High | `AuditClassification` enum に Phase 03 が出力する4つの分類値を追加 | `scripts/orchestrator/schemas.py` |
| BUG-SCH03 | Medium | Phase 02c の `output_fields` に `code_excerpt` を追加 | `scripts/orchestrator/config.py` |
| BUG-SCH04 | Low | `Severity` docstring の比較方向を修正（`CRITICAL < HIGH` → `CRITICAL > HIGH`） | `scripts/orchestrator/schemas.py` |
| BUG-SCH05/06 | Medium | テストのフィールド名を実際のスキーマに合わせて修正 | `tests/test_schemas_and_config.py` |

#### 第2回修正（9件）

| Bug ID | 重要度 | 内容 | 対象ファイル |
|--------|--------|------|-------------|
| BUG-SCH02 | High | `PropertyWithCode` に `populate_by_name=True` + エイリアス（`checklist_id`, `code_path`, `proof_trace`）+ `attack_scenario` フィールド + `_sync_fields` validator追加 | `scripts/orchestrator/schemas.py` |
| BUG-SCH07 | Medium | `PropertyWithCode.model_validate()` で `code_scope` が保持されることのテスト追加 | `tests/test_schemas_and_config.py` |
| BUG-SCH08 | High | Phase02 merge validatorが一方のリストを捨てる問題を、両リストマージ＋ `check_id` 重複排除に修正 | `scripts/orchestrator/schemas.py` |
| BUG-SCH09 | Medium | `review_verdict` の型を `str` → `ReviewVerdict | str` に拡張（不明な値でもバリデーションエラーにならない） | `scripts/orchestrator/schemas.py` |
| BUG-SCH10 | Medium | early exit `audit_trail` に `phase2_5_reachability_analysis` と `phase3_5_scope_filtering` エントリ追加 | `scripts/orchestrator/base.py` |
| BUG-SCH11 | Low | `ResultCollector` の `processed_ids` 追跡が正しく動作するテスト追加 | `tests/test_schemas_and_config.py` |
| BUG-SCH12 | Medium | テストの `sys.modules` 汚染を `patch.dict()` で適切にクリーンアップ | `tests/test_phase03_early_exit.py`, `tests/test_severity_gate.py` |
| BUG-SCH13 | Medium | テストのパス解決を `Path(__file__).resolve().parent.parent` に変更（CWD非依存） | `tests/test_phase03_early_exit.py`, `tests/test_severity_gate.py` |
| BUG-SCH14 | Medium | Phase02 `PartialMergeValidator` の5テストケース追加（空リスト/重複/混合など） | `tests/test_schemas_and_config.py` |

---

### CI/CD（18件）

#### 第1回修正（3件）

| Bug ID | 重要度 | 内容 | 対象ファイル |
|--------|--------|------|-------------|
| BUG-CI01 | High | 01e workflow で heredoc 内のインデント付き JSON が壊れる問題を `printf` 方式に修正 | `.github/workflows/01e-properties.yml` |
| BUG-CI02 | Medium | RQ1 benchmark workflow で git commit 前に `user.name`/`user.email` が未設定だった問題を修正 | `.github/workflows/benchmark-rq1-sherlock-eval.yml` |
| BUG-CI03 | Medium | `actions/upload-artifact@v6`（存在しない）を `@v4` に修正 | `.github/workflows/openhands-resolver.yml` |

#### 第2回修正（15件）

| Bug ID | 重要度 | 内容 | 対象ファイル |
|--------|--------|------|-------------|
| BUG-CI04 | High | benchmark-rq2-01-setup に `contents: write` 権限と `git push` ステップ追加 | `.github/workflows/benchmark-rq2-01-setup.yml` |
| BUG-CI05 | High | openhands `process.env.RESOLUTION_SUCCESS` を `steps.check_result.outputs.RESOLUTION_SUCCESS` に修正 | `.github/workflows/openhands-resolver.yml` |
| BUG-CI06 | Medium | benchmark-rq2-02-tools にステップ `id:` と結果サマリーステップ追加 | `.github/workflows/benchmark-rq2-02-tools.yml` |
| BUG-CI07 | Medium | ハードコードされたRHEL `SSL_CERT_FILE` パスを削除 | `.github/workflows/openhands-resolver.yml`, `.github/workflows/sweagent-issue-resolver.yml` |
| BUG-CI08 | Low | 02c workflow の空 `checkout_ref` に意図説明コメント追加 | `.github/workflows/02c-enrich-code.yml` |
| BUG-CI09 | Low | `workflow_call` バイパスの意図説明コメント追加 | `.github/workflows/openhands-resolver.yml` |
| BUG-CI10 | Medium | `fromJson(vars.OPENHANDS_MAX_ITER \|\| 200)` の型不整合を `\|\| '200'` に修正 | `.github/workflows/issue-resolver.yml` |
| BUG-CI11 | Medium | 02c workflow に `force_execute` boolean入力と `--force` フラグ追加 | `.github/workflows/02c-enrich-code.yml` |
| BUG-CI12 | Medium | 全workflowのハードコードされた `master` を `${{ github.event.repository.default_branch }}` に置換 | `.github/workflows/02c-enrich-code.yml`, `.github/workflows/03-audit-map.yml`, `.github/workflows/04-audit-review.yml` |
| BUG-CI13 | Medium | benchmark-rq2-03-evaluate に結果コミット＋プッシュステップ追加 | `.github/workflows/benchmark-rq2-03-evaluate.yml` |
| BUG-CI14 | High | 全workflowの `if: always()` を `if: success() \|\| failure()` に修正（キャンセル時の不要実行防止） | `.github/workflows/01a-discovery.yml`, `01b-subgraph.yml`, `01e-properties.yml`, `03-audit-map.yml`, `04-audit-review.yml` |
| BUG-CI15 | Medium | `rm -rf outputs/**/03_*` グロブを `find` コマンドに置換（安全な削除） | `.github/workflows/03-audit-map.yml`, `.github/workflows/04-audit-review.yml` |
| BUG-CI16 | Low | 01a-discovery の同期元ブランチ説明コメント追加 | `.github/workflows/01a-discovery.yml` |
| BUG-CI17 | Medium | openhands `ISSUE_NUMBER` の null/空ガード追加 | `.github/workflows/openhands-resolver.yml` |
| BUG-CI18 | Medium | sweagent トークンをCLI引数から環境変数に変更（ログ漏洩防止） | `.github/workflows/sweagent-issue-resolver.yml` |

---

### Benchmark（16件）

#### 第1回修正（1件）

| Bug ID | 重要度 | 内容 | 対象ファイル |
|--------|--------|------|-------------|
| BUG-BEN01 | High | `collect_branch_outputs.py` の `ROOT_DIR` が `parents[1]`（`benchmarks/`）を指していた問題を `parents[2]`（プロジェクトルート）に修正 | `benchmarks/scripts/collect_branch_outputs.py` |

#### 第2回修正（15件）

| Bug ID | 重要度 | 内容 | 対象ファイル |
|--------|--------|------|-------------|
| BUG-BEN02 | High | `classification_filter=None` かつ `include_bug_bounty=True` 時に `return False` していた問題を `return True` に修正 | `benchmarks/rq1/matchers.py` |
| BUG-BEN03 | Medium | メトリクス名 `cliffs_delta` を正確な `paired_proportion_diff` にリネーム（docstring追加） | `benchmarks/metrics/stats.py` |
| BUG-BEN04 | Medium | `run_semgrep` にサンプルの `language`/`lang` フィールドからの拡張子推定機能追加 | `benchmarks/runners/run_semgrep.py` |
| BUG-BEN05 | Medium | コード欠損時の `None` チェック追加（警告ログ出力して continue） | `benchmarks/runners/run_semgrep.py` |
| BUG-BEN06 | Medium | Semgrep JSON出力の `json.loads()` に `JSONDecodeError` ハンドリング追加 | `benchmarks/runners/run_semgrep.py` |
| BUG-BEN07 | Low | `_TS_RE` 正規表現の `B<batch>` と `_<seq>` 部分をオプショナルに修正 | `benchmarks/scripts/collect_branch_outputs.py` |
| BUG-BEN08 | Medium | コードフィールドのフォールバック検索 `CODE_KEYS = ["func", "before", "after", "code"]` 追加 | `benchmarks/runners/run_semgrep.py` |
| BUG-BEN09 | Low | `collect_phase_logs` の `total_tokens` に `cache_read_input_tokens`/`cache_creation_input_tokens` 追加 | `benchmarks/scripts/collect_branch_outputs.py` |
| BUG-BEN10 | Medium | `loaders.py` のエラーカウントがハードコード `0` だった問題を実際のエラー数に修正 | `benchmarks/tools/loaders.py` |
| BUG-BEN11 | Medium | dict型ペイロードの `"results"` キー抽出＋リストラップ処理追加 | `benchmarks/tools/loaders.py` |
| BUG-BEN12 | Low | `registry.py` の不整合パターン `"security_agent_results.json"` 削除 | `benchmarks/tools/registry.py` |
| BUG-BEN13 | Medium | bootstrap CI計算の `int()` を `round()` に修正（丸め誤差防止） | `benchmarks/metrics/stats.py` |
| BUG-BEN14 | Medium | rq2 evaluate で未知の `vul_type` 値に対する警告付き else 分岐追加 | `benchmarks/rq2/evaluate.py` |
| BUG-BEN15 | Medium | Stage 2キーワードマッチの閾値 `overlap >= 3` をパラメータ `keyword_min_overlap` に変更 | `benchmarks/rq1/matchers.py` |
| BUG-BEN16 | Low | `fetch_vul4j.sh` のインラインPythonをシングルクォート heredoc に修正（変数展開防止） | `benchmarks/datasets/fetch_vul4j.sh` |

---

## テスト結果

```
236 passed in 5.10s
```

- 既存231テスト全パス + 新規5テスト追加（SCHグループ）
- リグレッションなし
- 4並列エージェントの修正をパッチマージ後、コンフリクトなし

## 変更ファイル一覧（45ファイル）

### 第1回コミット（12ファイル）
```
.github/workflows/01e-properties.yml
.github/workflows/benchmark-rq1-sherlock-eval.yml
.github/workflows/openhands-resolver.yml
benchmarks/scripts/collect_branch_outputs.py
scripts/orchestrator/__init__.py
scripts/orchestrator/base.py
scripts/orchestrator/config.py
scripts/orchestrator/resume.py
scripts/orchestrator/runner.py
scripts/orchestrator/schemas.py
scripts/run_phase.py
tests/test_schemas_and_config.py
```

### 第2回コミット（33ファイル）
```
.github/workflows/01a-discovery.yml
.github/workflows/01b-subgraph.yml
.github/workflows/01e-properties.yml
.github/workflows/02c-enrich-code.yml
.github/workflows/03-audit-map.yml
.github/workflows/04-audit-review.yml
.github/workflows/benchmark-rq2-01-setup.yml
.github/workflows/benchmark-rq2-02-tools.yml
.github/workflows/benchmark-rq2-03-evaluate.yml
.github/workflows/issue-resolver.yml
.github/workflows/openhands-resolver.yml
.github/workflows/sweagent-issue-resolver.yml
benchmarks/datasets/fetch_vul4j.sh
benchmarks/metrics/stats.py
benchmarks/rq1/evaluate.py
benchmarks/rq1/matchers.py
benchmarks/rq2/evaluate.py
benchmarks/rq2/generate_report.py
benchmarks/runners/run_semgrep.py
benchmarks/scripts/collect_branch_outputs.py
benchmarks/tools/loaders.py
benchmarks/tools/registry.py
scripts/orchestrator/base.py
scripts/orchestrator/collector.py
scripts/orchestrator/resume.py
scripts/orchestrator/runner.py
scripts/orchestrator/schemas.py
scripts/orchestrator/watchdog.py
scripts/run_phase.py
tests/test_phase03_early_exit.py
tests/test_schemas_and_config.py
tests/test_severity_gate.py
tests/test_watchdog_cache_tokens.py
```

## 対応状況サマリー

| カテゴリ | kijaku.md記載数 | 本PR対応 | 別PR対応 | 残件 |
|---------|---------------|---------|---------|------|
| SEC（セキュリティ） | 4 | 0 | 4（別PR済） | 0 |
| ORC（Orchestrator） | 19 | 19 | 0 | 0 |
| SCH（Schema/Config） | 14 | 13 | 0 | 0* |
| CI（CI/CD） | 18 | 18 | 0 | 0 |
| BEN（Benchmark） | 16 | 16 | 0 | 0 |
| **合計** | **84** | **66** | **4** | **0** |

*SCH: 一部は重複としてカウント（SCH05/SCH06を1件として対応）

## レビュー観点

### 第1回修正分
1. `PhaseAbortError` の導入により `sys.exit()` が全て例外に置換されたこと
2. `resume.py` の正規表現修正が既存のレジューム動作に影響しないこと
3. Phase04 の dict ベース重複排除で `property_id` がキーとして適切であること
4. CI workflow の変更が各環境で正しく動作すること

### 第2回修正分
5. `asyncio.Semaphore`/`Lock` の遅延初期化がイベントループ内で正しく行われること
6. `num_turns` の計算変更（メッセージ数→ターン数）が下流の処理に影響しないこと
7. `PropertyWithCode` のエイリアスと `_sync_fields` validator が既存データと互換であること
8. Phase02 merge validator の両リストマージが `check_id` 重複排除で正しく動作すること
9. `always()` → `success() || failure()` 変更がCI/CDの意図したフローを壊さないこと
10. `master` → `default_branch` 変数化がリポジトリのデフォルトブランチ設定と一致すること
11. sweagent トークンの環境変数化でCI実行時にトークンが正しく渡されること
