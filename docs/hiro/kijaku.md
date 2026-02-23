# SPECA プロジェクト 脆弱性・バグ包括レポート

**作成日**: 2026-02-23
**対象**: プロジェクト全体（オーケストレーター、ベンチマーク、CI/CD、スキーマ、テスト）
**発見総数**: セキュリティ脆弱性 17件 + ロジックバグ 53件 = **70件**

---

# ロジックバグ — オーケストレーター

---

### BUG-ORC01: sys.exit()がパイプラインエラー処理をバイパス 【High】

## 概要
`orchestrator.run()` 内部の `sys.exit(1)` が `SystemExit`（`BaseException`）を送出し、`except Exception` で捕捉されないためパイプライン全体が即座に終了する。

## 再現手順
1. Phase 01e を実行するが `BUG_BOUNTY_SCOPE.json` が存在しない状態
2. 失敗するコマンド：
   ```bash
   uv run python scripts/run_phase.py --phase 01a 01b 01e
   ```

## 期待する挙動
01e の失敗がレポートされ、パイプラインが適切にクリーンアップされる。

## 現状の挙動（ログ/エラー）
```text
# scripts/run_phase.py L168-193 の except Exception では SystemExit を捕捉できない
# base.py L679-686 で sys.exit(1) が呼ばれると即終了
```

## 受け入れ条件
* [ ] `sys.exit(1)` を カスタム例外（例: `PhaseAbortError`）に変更
* [ ] `run_phase.py` で `except (Exception, SystemExit)` または `except BaseException` で捕捉
* [ ] `uv run python -m pytest` が成功する（exit code 0）

## OpenHandsへの指示
@openhands-agent
* `base.py` の `sys.exit(1)` を `raise PhaseAbortError(msg)` に変更（新しい例外クラス定義）
* `run_phase.py` のエラーハンドリングで `PhaseAbortError` も捕捉

---

### BUG-ORC02: Early-Exit結果がディスクに保存されない 【High】

## 概要
Phase 03/04 の `apply_early_exit` で計算されたスキップ結果がPARTIALファイルに保存されず、resume や下流フェーズで認識されない。

## 再現手順
1. Phase 03 を実行、一部アイテムが `out-of-scope` で早期終了
2. Phase 03 を再実行（resume）
3. 失敗するコマンド：
   ```bash
   uv run python scripts/run_phase.py --phase 03
   # → 早期終了済みアイテムが再処理される
   ```

## 期待する挙動
早期終了結果もPARTIALファイルに保存され、resume で重複処理されない。

## 現状の挙動（ログ/エラー）
```text
# base.py L197-214: early_exit_results は計算されるが save_partial() が呼ばれない
# resume.py はPARTIALファイルしかスキャンしないため、早期終了アイテムが未処理扱いになる
```

## 受け入れ条件
* [ ] `apply_early_exit` の結果を `collector.save_partial()` で保存
* [ ] resume スキャンでこれらのアイテムが検出されること
* [ ] テスト追加

## OpenHandsへの指示
@openhands-agent
* `base.py` の `run()` メソッド内で `early_exit_results` を `self.collector.save_partial()` で保存
* PARTIALファイル名に `_EARLYEXIT_` プレフィックスを付与して区別

---

### BUG-ORC03: resume.py 正規表現の大文字/小文字不一致 【High】

## 概要
`get_incomplete_batches()` のディレクトリ名マッチングが大文字 `W`/`B` を期待するが、実際のディレクトリ名は小文字 `w`/`b`。全バッチが「不完全」と誤判定される。

## 再現手順
1. Phase 01b を実行（ディレクトリモード）
2. cleanup dry-run を実行
3. 失敗するコマンド：
   ```bash
   uv run python scripts/run_phase.py --phase 01b --cleanup-dry-run
   # → 全バッチディレクトリが "incomplete" と表示される
   ```

## 期待する挙動
完了済みバッチは incomplete として報告されない。

## 現状の挙動（ログ/エラー）
```python
# resume.py L146: 大文字パターン
dir_prefix_match = re.search(r"(W\d+B\d+)", batch_dir.name)
# runner.py L355: 小文字で作成
batch_output_dir = self.output_dir / "graphs" / f"batch_w{worker_id}b{batch_index}_{timestamp}"
# → dir_prefix_match は常に None
```

## 受け入れ条件
* [ ] 正規表現を `r"([Ww]\d+[Bb]\d+)"` に変更、または `re.IGNORECASE` フラグ追加
* [ ] `uv run python -m pytest` が成功する（exit code 0）
* [ ] テスト追加: 小文字ディレクトリ名が正しくマッチすることを検証

## OpenHandsへの指示
@openhands-agent
* `resume.py` L146 の正規表現に `re.IGNORECASE` フラグを追加
* L135 の PARTIAL ファイル側の正規表現との整合性を確認

---

### BUG-ORC04: --force --target が全フェーズの出力を削除 【Medium】

## 概要
`--force` と `--target` を併用すると、ターゲットフェーズだけでなく依存チェーン上の全フェーズの出力が削除される。

## 再現手順
1. Phase 01a〜02c まで完了した状態
2. 失敗するコマンド：
   ```bash
   uv run python scripts/run_phase.py --target 03 --force
   # → 01a, 01b, 01e, 02c の出力も全て削除される
   ```

## 期待する挙動
`--force` はターゲットフェーズ（03）の出力のみ削除し、上流フェーズの出力は保持。

## 現状の挙動（ログ/エラー）
```text
# run_phase.py L196-295: 依存チェーン上の全フェーズに対して cleanup が実行される
```

## 受け入れ条件
* [ ] `--force` 時はターゲットフェーズのみ cleanup
* [ ] 上流フェーズの出力は保持
* [ ] テスト追加

## OpenHandsへの指示
@openhands-agent
* `--target` + `--force` の場合、cleanup をターゲットフェーズのみに限定するロジック追加

---

### BUG-ORC05: Phase04 load_items が重複排除しない 【Medium】

## 概要
Phase 02c/03 は `dict` で property_id をキーにして重複排除するが、Phase 04 は `list` を使用するため重複アイテムがロードされる。

## 再現手順
1. Phase 03 を部分的に再実行して同じ property_id の結果が複数 PARTIAL に存在
2. Phase 04 を実行
3. 失敗するコマンド：
   ```bash
   uv run python scripts/run_phase.py --phase 04
   # → 同一 property_id が複数回レビューされ、矛盾する結果が出る
   ```

## 期待する挙動
property_id ベースで重複排除された一意なアイテムのみ処理。

## 現状の挙動（ログ/エラー）
```python
# base.py L1055-1096: Phase04Orchestrator.load_items は items = [] (リスト)
# Phase02c/03 は items = {} (dict) で重複排除
```

## 受け入れ条件
* [ ] Phase 04 の `load_items` を dict ベースの重複排除に変更
* [ ] テスト追加

## OpenHandsへの指示
@openhands-agent
* `Phase04Orchestrator.load_items()` で `items` を dict（キー: `property_id`）に変更

---

### BUG-ORC06: _enrich_with_subgraph_context が Phase 01e でノーオペ 【Medium】

## 概要
Phase 01e のアイテムには `subgraph_file` / `subgraph_id` キーがなく `file_path` のみのため、サブグラフコンテキスト注入が実質的に何もしない。

## 受け入れ条件
* [ ] Phase 01e のアイテムに `subgraph_file` / `subgraph_id` を設定するか、別のエンリッチメントロジックを実装

---

### BUG-ORC07: asyncio プリミティブがイベントループ外で生成 【Medium】

## 概要
`asyncio.Semaphore` と `asyncio.Lock` が `__init__` で生成されるが、Python 3.9 ではイベントループ外での生成は `DeprecationWarning` / エラーになる。

## 受け入れ条件
* [ ] `asyncio.Semaphore` / `asyncio.Lock` の生成を `run()` メソッド内（ループ起動後）に移動
* [ ] Python 3.9 互換性の確保

---

### BUG-ORC08: batch_index が 1 始まり（off-by-one）【Low】

`base.py` L440-442 でプリインクリメントにより batch_index が 1 から開始。ログ/ファイル名に影響。

### BUG-ORC09: LogWatcher のファイルオフセット比較 【Low】

`watchdog.py` L234-242 でテキストモードオフセットとバイトベースの stat サイズを比較。

### BUG-ORC10: プロンプト先頭の空白が二重 lstrip で削除 【Low】

`runner.py` L833-835 で意図的な先頭空白が削除される。

### BUG-ORC11: cleanup dry-run のカウントが不正確 【Low】

`resume.py` L251-307 でディレクトリモードのログファイルが二重カウントされる。

### BUG-ORC12: phase_id "02" のデッドコード 【Low】

`runner.py` L898: `"02"` は存在しないフェーズID（正しくは `"02c"`）。

### BUG-ORC13: LogWatcher が stop() 後の最終チャンクを見逃す 【Low】

`watchdog.py` L234-259

### BUG-ORC14: .claude/debug/latest が並行バッチ間で汚染 【Low】

`runner.py` L874-889

### BUG-ORC15: fallback num_turns がメッセージ数でカウント 【Low】

`watchdog.py` L617: ターン数ではなくメッセージ数で過大カウント。

### BUG-ORC16: PARTIAL タイムスタンプが queue/log と不一致 【Low】

`collector.py` L72: 独立した `time.time()` 使用。

### BUG-ORC17: 例外ハンドラの (0,0) worker_id/batch_index 【Low】

`base.py` L491-493: デバッグ困難。

### BUG-ORC18: 到達不能な KeyError 例外ハンドラ 【Low】

`runner.py` L724, L933

### BUG-ORC19: _build_prompt の空白含む引数が曖昧 【Low】

`runner.py` L771

---

# ロジックバグ — ベンチマーク/評価

---

### BUG-BEN01: collect_branch_outputs.py の ROOT_DIR が間違い 【High】

## 概要
`ROOT_DIR = Path(__file__).resolve().parents[1]` が `benchmarks/` を指し、デフォルト出力パスが `benchmarks/benchmarks/results/...` になる。

## 再現手順
1. デフォルト引数でスクリプトを実行
2. 失敗するコマンド：
   ```bash
   uv run python benchmarks/scripts/collect_branch_outputs.py
   # → benchmarks/benchmarks/results/ に書き込もうとする
   ```

## 期待する挙動
プロジェクトルートが `ROOT_DIR` となり `benchmarks/results/` に書き込む。

## 現状の挙動（ログ/エラー）
```python
# collect_branch_outputs.py L13
ROOT_DIR = Path(__file__).resolve().parents[1]  # → benchmarks/
# L385: default = ROOT_DIR / "benchmarks" / "results" / ...
# → benchmarks/benchmarks/results/...（二重ネスト）
```

## 受け入れ条件
* [ ] `parents[1]` → `parents[2]` に修正
* [ ] `uv run python -m pytest` が成功する（exit code 0）

## OpenHandsへの指示
@openhands-agent
* L13 を `parents[2]` に変更

---

### BUG-BEN02: is_selected_audit_item のフィルタロジック誤り 【Medium】

## 概要
`include_bug_bounty=True` + `classification_filter=None` の場合、バグバウンティ対象でない全アイテムが誤って除外される。

## 再現手順
1. `--audit-include-bug-bounty` フラグのみで（`--audit-classifications` なし）評価実行
2. 失敗するコマンド：
   ```bash
   uv run python benchmarks/rq1/evaluate_audit.py --audit-include-bug-bounty
   ```

## 期待する挙動
全アイテムが含まれる（分類フィルタなしのため）。

## 現状の挙動（ログ/エラー）
```python
# matchers.py L137-139
if include_bug_bounty and raw.get("bug_bounty_eligible") is True:
    return True
if classification_filter is None:
    return False  # ← バグバウンティ対象でないアイテムが全て除外
```

## 受け入れ条件
* [ ] `classification_filter is None and not include_bug_bounty` の場合に `return True`（全含む）
* [ ] `include_bug_bounty=True` + `classification_filter is None` でも非バグバウンティアイテムを含む
* [ ] テスト追加

## OpenHandsへの指示
@openhands-agent
* ロジックの修正: `classification_filter is None` かつ `include_bug_bounty` がFalse相当の場合のみ全含む
* `include_bug_bounty=True` は追加フィルタとして機能するよう修正

---

### BUG-BEN03: Cliff's Delta の計算が誤ラベル 【Medium】

## 概要
`effect_size_cliffs_delta` は `(b-c)/n` を計算するが、これは実際のCliff's Delta（ペアワイズ比較）ではない。

## 再現手順
1. ベンチマーク評価を実行

## 期待する挙動
正しいCliff's Delta計算、またはメトリクス名の修正。

## 現状の挙動（ログ/エラー）
```python
# metrics/stats.py L22-35
delta = (b - c) / n  # これは Cliff's Delta ではない
```

## 受け入れ条件
* [ ] 正しいCliff's Delta実装（ペアワイズ比較）に修正、またはメトリクス名を `"paired_proportion_diff"` に変更

---

### BUG-BEN04: Semgrepランナーが全ファイルを .c 拡張子で作成 【Medium】

## 概要
`run_semgrep.py` L39 で全一時ファイルが `.c` 拡張子。C++/Java コードの解析が不正確になる。

## 受け入れ条件
* [ ] データセットの `language` フィールドから適切な拡張子を選択
* [ ] デフォルトは `.c` のまま

---

### BUG-BEN05: sample.get("func") が None の場合にクラッシュ 【Medium】

## 概要
`run_semgrep.py` L36-40: `func` キーがないデータセットレコードで `write_text(None)` が TypeError。

## 受け入れ条件
* [ ] None チェック追加、スキップ + エラーログ出力

---

### BUG-BEN06: Semgrep の非JSON出力でクラッシュ 【Medium】

## 概要
`run_semgrep.py` L59: Semgrepがエラーメッセージを stdout に出力した場合 `json.loads()` が JSONDecodeError。

## 受け入れ条件
* [ ] try-except で JSONDecodeError を捕捉、エラーレコードとして記録

---

### BUG-BEN07: タイムスタンプ正規表現がファイル名にマッチしない 【Medium】

## 概要
`collect_branch_outputs.py` L53: 正規表現が `_W0_ts_seq` パターンを期待するが実ファイルは `_W0B1_ts` パターン。`estimate_phase_timing` が常に空 dict を返す。

## 受け入れ条件
* [ ] 正規表現を `r"_W(?P<worker>\d+)B(?P<batch>\d+)_(?P<ts>\d{9,})\.json$"` に修正

---

### BUG-BEN08: CVEfixesデータセットがSemgrepランナーと非互換 【Medium】

## 概要
CVEfixesは `before`/`after` キーにコードを格納するが、Semgrepランナーは `func` キーを期待。

## 受け入れ条件
* [ ] Semgrepランナーに `CODE_KEYS` フォールバック実装（bench_utils.py の `extract_code()` 利用）

---

### BUG-BEN09: cache_read/cache_creation トークンが集計から欠落 【Low-Medium】

`collect_branch_outputs.py` L262-268: キャッシュトークンキーが `total_tokens` dict に含まれていない。

### BUG-BEN10: Semgrepローダーが error_count を常に 0 返却 【Low】

`loaders.py` L26

### BUG-BEN11: Semgrepローダーが dict ペイロードでクラッシュ 【Low】

`loaders.py` L19

### BUG-BEN12: security_agent パターンが JSONL ローダーと不整合 【Low】

`registry.py` L53-56

### BUG-BEN13: Bootstrap CI が int() 切り捨てでバイアス 【Low】

`stats.py` L49-50

### BUG-BEN14: vul_type の非 0/1 整数値でサイレントフォールスルー 【Low】

`evaluate.py` L60-68

### BUG-BEN15: keyword_min_overlap パラメータが Stage 2 に効かない 【Low】

`matchers.py` L345

### BUG-BEN16: fetch_vul4j.sh のインラインPythonでシェル変数が未エスケープ 【Low】

`fetch_vul4j.sh` L57-69

---

# ロジックバグ — CI/CDワークフロー

---

### BUG-CI01: Heredocで BUG_BOUNTY_SCOPE.json が不正JSON生成 【High】

## 概要
`01e-properties.yml` のheredocがインデント付きで `BUG_BOUNTY_SCOPE.json` を生成し、パース失敗する。

## 再現手順
1. Phase 01e ワークフローを bug_bounty_scope 入力付きでディスパッチ
2. 失敗するコマンド：
   ```bash
   # ワークフロー内で生成された BUG_BOUNTY_SCOPE.json を python で読み込み
   python -c "import json; json.load(open('outputs/BUG_BOUNTY_SCOPE.json'))"
   ```

## 期待する挙動
有効なJSONファイルが生成される。

## 現状の挙動（ログ/エラー）
```yaml
# 01e-properties.yml L137-139
          cat > outputs/BUG_BOUNTY_SCOPE.json << 'EOF'
          ${{ inputs.bug_bounty_scope }}
          EOF
# → EOF デリミタのインデント問題で不正JSON
```

## 受け入れ条件
* [ ] heredoc の代わりに `echo '${{ inputs.bug_bounty_scope }}' > outputs/BUG_BOUNTY_SCOPE.json` を使用
* [ ] または `<<-'EOF'`（タブ除去 heredoc）+ タブインデントに変更

## OpenHandsへの指示
@openhands-agent
* heredoc を `printf '%s\n' '${{ inputs.bug_bounty_scope }}' > outputs/BUG_BOUNTY_SCOPE.json` に変更

---

### BUG-CI02: benchmark-rq1-sherlock-eval で git user.name/email 未設定 【High】

## 概要
コミット実行前に `git config user.name/email` が設定されず、コミットが常に失敗する。

## 再現手順
1. Sherlock 評価ワークフローを実行
2. 結果のプッシュステップで失敗

## 期待する挙動
他のワークフロー同様、git ユーザー設定がある。

## 現状の挙動（ログ/エラー）
```text
# benchmark-rq1-sherlock-eval.yml L134-142
# "Prepare Git" ステップが存在しない（01a,01b等には存在）
fatal: unable to auto-detect email address
```

## 受け入れ条件
* [ ] "Prepare Git" ステップを追加（`git config user.name "github-actions[bot]"` 等）

## OpenHandsへの指示
@openhands-agent
* commit/push ステップの前に git user 設定ステップを追加

---

### BUG-CI03: actions/upload-artifact@v6 は存在しない 【High】

## 概要
`openhands-resolver.yml` L308 が `@v6` を参照するが、最新は `@v4`。

## 受け入れ条件
* [ ] `@v6` → `@v4` に修正

## OpenHandsへの指示
@openhands-agent
* `openhands-resolver.yml` L308 の `@v6` を `@v4` に変更

---

### BUG-CI04: benchmark-rq2-01-setup でブランチが未プッシュ 【High】

## 概要
新規ブランチが作成されるが remote にプッシュされない。下流の `benchmark-rq2-02-tools.yml` がブランチをチェックアウトしようとして失敗する。

## 再現手順
1. `benchmark-rq2-01-setup` で `branch` 入力を空にして実行
2. 下流の `benchmark-rq2-02-tools` を生成されたブランチ名で実行
3. チェックアウト失敗

## 期待する挙動
ブランチが remote にプッシュされ、下流ワークフローでチェックアウト可能。

## 受け入れ条件
* [ ] ブランチ作成後に `git push origin ${BRANCH}` を追加

## OpenHandsへの指示
@openhands-agent
* Summary ステップの前に `git push origin "${BRANCH}"` ステップを追加

---

### BUG-CI05: RESOLUTION_SUCCESS が env ではなく output 参照ミス 【Medium】

`openhands-resolver.yml` L374: `process.env.RESOLUTION_SUCCESS` → `steps.check_result.outputs.RESOLUTION_SUCCESS`

### BUG-CI06: continue-on-error が全ツールランナーの失敗を隠蔽 【Medium】

`benchmark-rq2-02-tools.yml` L180等: 5つ全てのランナーステップ。

### BUG-CI07: SSL証明書パスがRHEL/CentOS固有 【Medium】

`openhands-resolver.yml` L286,329: Ubuntu では `/etc/ssl/certs/ca-certificates.crt`。

### BUG-CI08: checkout_ref が常に空文字列 【Low】

`02c-enrich-code.yml` L110,116

### BUG-CI09: github.event_name == 'workflow_call' が常にマッチしない 【Low】

`openhands-resolver.yml` L68: デッドコード。

### BUG-CI10: fromJson のバリデーション欠如 【Low】

`issue-resolver.yml` L25

### BUG-CI11: 02c-enrich-code に force_execute 入力なし 【Low】

resume/増分実行が不可能。

### BUG-CI12: master ブランチ名がハードコード 【Low】

`02c`, `03`, `04` ワークフロー: `main` への改名時に壊れる。

### BUG-CI13: benchmark-rq2-03-evaluate が結果を未プッシュ 【Low】

アーティファクト/キャッシュのみで git history に残らない。

### BUG-CI14: if: always() で壊れた状態がプッシュされる可能性 【Low】

`01a` 等の "Push Results" ステップ。

### BUG-CI15: ** glob が globstar 未有効で動作しない 【Low】

`03-audit-map.yml` L133, `04-audit-review.yml` L122

### BUG-CI16: スクリプト同期元ブランチの不整合リスク 【Low】

`01a-discovery.yml` L59

### BUG-CI17: PR番号参照の脆弱性（workflow_call経由）【Low】

`openhands-resolver.yml` L123-128

### BUG-CI18: sweagent-resolver でトークンがCLI引数に露出 【Low】

`sweagent-issue-resolver.yml` L48

---

# ロジックバグ — スキーマ/テスト

---

### BUG-SCH01: AuditClassification Enum と Phase 03 出力値の不一致 【High】

## 概要
`AuditClassification` enum が定義する値（`vulnerable`, `safe`, `inconclusive`）と Phase 03 プロンプトが実際に出力する値（`vulnerability`, `not-a-vulnerability`, `potential-vulnerability`, `informational`）が一致しない。

## 再現手順
1. Phase 03 を実行
2. 出力の classification 値を enum で検証
3. 失敗するコマンド：
   ```bash
   uv run python -c "
   from scripts.orchestrator.schemas import AuditClassification
   AuditClassification('vulnerability')  # → ValueError
   "
   ```

## 期待する挙動
enum 値が実際の出力と一致する。

## 現状の挙動（ログ/エラー）
```python
# schemas.py L102-107
class AuditClassification(str, Enum):
    VULNERABLE = "vulnerable"      # 実際: "vulnerability"
    SAFE = "safe"                  # 実際: "not-a-vulnerability"
    INCONCLUSIVE = "inconclusive"  # 実際: "potential-vulnerability"
    # "informational" が欠落
```

## 受け入れ条件
* [ ] enum 値を Phase 03 プロンプトの出力値に合わせる
* [ ] `INFORMATIONAL` メンバーを追加
* [ ] `uv run python -m pytest` が成功する（exit code 0）

## OpenHandsへの指示
@openhands-agent
* `AuditClassification` の値を更新、テストも合わせて修正

---

### BUG-SCH02: AuditMapItem スキーマと Phase 03 プロンプト出力の乖離 【High】

## 概要
`AuditMapItem` のフィールド名・型が Phase 03 プロンプトの出力スキーマと全く異なる。

## 現状の挙動（ログ/エラー）
```text
# スキーマ: check_id, code_scope(CodeScope), code_snippet, audit_trail(AuditTrail)
# プロンプト出力: checklist_id, code_path(str), proof_trace, attack_scenario
```

## 受け入れ条件
* [ ] スキーマをプロンプト出力に合わせて更新、または alias を追加
* [ ] cross-phase バリデーションテストが全パス

---

### BUG-SCH03: Phase 02c output_fields が code_excerpt を除外 【Medium】

## 概要
Phase 03 が `context_fields` に `code_excerpt` を期待するが、Phase 02c の `output_fields` に含まれておらず保存時に除去される。

## 受け入れ条件
* [ ] Phase 02c `output_fields` に `"code_excerpt"` を追加
* [ ] または Phase 03 `context_fields` から `"code_excerpt"` を削除

## OpenHandsへの指示
@openhands-agent
* `config.py` の Phase 02c output_fields リストに `"code_excerpt"` を追加

---

### BUG-SCH04: Severity docstring が実際の比較動作と逆 【Medium】

## 概要
docstring: `Severity.CRITICAL < Severity.HIGH` is `True` → 実際は `False`

## 受け入れ条件
* [ ] docstring を `Severity.CRITICAL > Severity.HIGH is True` に修正

---

### BUG-SCH05: テストが存在しないフィールド名を使用 【Medium】

## 概要
`StrideAnalysisItem` テストが `affected_boundary` を渡すが、正しいフィールドは `trust_boundary_id`。Pydantic v2 が黙って無視するためテストは通るが、実質テスト無効。

## 受け入れ条件
* [ ] `affected_boundary` → `trust_boundary_id` に修正
* [ ] アサーションに `stride.trust_boundary_id == "tb-001"` を追加

---

### BUG-SCH06: TrustAssumption テストが description を text の代わりに使用 【Medium】

`test_schemas_and_config.py` L544: `description` → `text` に修正。

### BUG-SCH07: cross-phase テストが code_scope の消失を検出しない 【Medium】

`test_schemas_and_config.py` L882-898: `validate_property` が `Property`（親クラス）で検証するため `code_scope` が消失。

### BUG-SCH08: Phase02Partial のマージバリデータが両方存在時にデータ消失 【Low】

`schemas.py` L360-365: `checklist` + `checklist_items` 両方指定時に `checklist_items` が消失。

### BUG-SCH09: ReviewVerdict enum が未使用（str 型で定義） 【Low】

`schemas.py` L110-114, L476: enum が存在するが実際のフィールドは `str`。

### BUG-SCH10: Early Exit 結果に audit_trail サブフェーズが欠落 【Low】

`base.py` L1013-1028: `phase2_5_reachability_analysis`, `phase3_5_scope_filtering` が欠落。

### BUG-SCH11: ResultCollector テストが processed_ids 追跡を検証しない 【Low】

`test_schemas_and_config.py` L1181-1193

### BUG-SCH12: sys.modules モックがテストセッション全体を汚染 【Low】

`test_phase03_early_exit.py` L10-13, `test_severity_gate.py` L13-16

### BUG-SCH13: CWD依存の sys.path 操作 【Low】

`test_phase03_early_exit.py` L7, `test_severity_gate.py` L9

### BUG-SCH14: Phase02Partial マージバリデータのテストカバレッジ欠如 【Low】

---

# サマリーテーブル

| カテゴリ | Critical | High | Medium | Low | 計 |
|----------|----------|------|--------|-----|-----|
| セキュリティ脆弱性 | 4 | 5 | 6 | 2 | **17** |
| オーケストレーター | — | 3 | 4 | 12 | **19** |
| ベンチマーク/評価 | — | 1 | 7 | 8 | **16** |
| CI/CDワークフロー | — | 4 | 3 | 11 | **18** |
| スキーマ/テスト | — | 2 | 5 | 7 | **14** |
| **合計** | **4** | **15** | **25** | **40** | **84** |

---
