過去のissiuse
actions/checkout が EACCES で失敗する問題のメモ #63
Open
Open
actions/checkout が EACCES で失敗する問題のメモ
#63
@grandchildrice
Description
grandchildrice
opened 13 hours ago
現象
self-hosted runner で 03. Audit Map 実行時、actions/checkout@v4 のクリーンアップで EACCES: permission denied, unlink benchmarks/__pycache__/__init__.cpython-311.pyc が発生しジョブが停止する。

該当箇所: https://github.com/NyxFoundation/security-agent/actions/runs/22278847556/job/64445651870#:~:text=Error%3A%20File,Prompts%20from%20Remote

再現手順
master ブランチで benchmark-rq2-02-tools.yml（RQ2 step2）を実行。
同じ runner ワークスペースで 03-audit-map.yml を実行。
原因
RQ2 step2 の Semgrep ステップで docker run -v "$PWD":/app ... を root ユーザのまま実行しており、コンテナ内で生成された benchmarks/__pycache__/*.pyc がホスト側で root 所有になる。次のジョブの checkout が削除できず失敗。

影響範囲
self-hosted runner 共有ワークスペース上のすべてのブランチ。

暫定回避策
ジョブ前に sudo chown -R $USER:$USER "$RUNNER_WORKSPACE" で所有権を戻してから実行。

恒久対応案
benchmark-rq2-02-tools.yml の Semgrep 実行ステップに --user $(id -u):$(id -g) を付ける。例:

UIDGID="$(id -u):$(id -g)"
docker run --rm --user "$UIDGID" -v "$PWD":/app security-agent-benchmark \
  python3 /app/benchmarks/runners/run_semgrep.py \
    --dataset "/app/${DATASET_PATH}" \
    --output "/app/${RESULTS_DIR}/semgrep_results.json" \
    --timeout "${{ inputs.tool_timeout }}"
（他の docker run も同様にユーザ指定を推奨）

備考
エフェメラル runner 運用や定期的なワークスペース掃除でも再発防止可能。

進行状況


Step 1: データセット取得の動作確認とキャッシュ整備

Step 2: 静的ツールのベンチマーク実行とキャッシュ保存

Step 3: security-agent のベンチマーク実行

Step 4: 評価と結果の可視化

Step 5: 再実験のフロー
対象ディレクトリ: benchmarks/rq2/, benchmarks/runners/, benchmarks/datasets/, .github/workflows/benchmark-rq2-*.yml

1. RQ2 ベンチマークの概要
RQ2（Research Question 2）は、「security-agent が従来の静的解析ツールおよびファジングベースラインと比較して、ラベル付けされた脆弱性データセット上でどの程度の性能を発揮するか」を定量的に評価するベンチマークです。

1.1 評価対象データセット
データセット	言語	規模	取得元	用途
PrimeVul	C/C++	数万件のペア	Hugging Face	メインデータセット（デフォルト）
CVEfixes	C/C++, Java, Python 等	分散OSSのCVEパッチ	Zenodo (v1.0.8)	分散システム特化の補足評価
Vul4J	Java	数百件のペア	Zenodo	Java特化の補足評価
各データセットは「脆弱なコード（vulnerable）」と「修正済みコード（clean）」のペアとして整形され、pair_id で紐付けられた JSONL 形式で保存されます。

1.2 評価対象ツール
ツール名	種別	実行スクリプト	結果ファイル
semgrep	静的解析	runners/run_semgrep.py	semgrep_results.json
codeql	静的解析	runners/run_codeql.py	codeql_results.jsonl
security_agent	LLMエージェント	runners/run_security_agent.py	security_agent_results.jsonl
llm_baseline	LLMベースライン	runners/run_llm_baseline.py	llm_baseline_results.jsonl
static_baseline	静的解析（Infer等）	runners/run_static_baseline.py	static_baseline_results.jsonl
1.3 評価指標
benchmarks/rq2/evaluate.py が以下の指標を計算します。

指標	説明
Precision / Recall / F1	標準的な二値分類指標
Coverage	スコアリングされたサンプル数 / 全サンプル数
Pairwise Accuracy	ペア単位の正解率（脆弱→True かつ clean→False の割合）
CWE Coverage	CWEカテゴリごとの再現率
Unique Detections	security-agent のみが検出した脆弱性
McNemar Exact Test	ツール間の有意差検定
Cliff's Delta	効果量（negligible / small / medium / large）
Bootstrap CI	95% 信頼区間（2000サンプル）
1.4 キャッシュ設計
すべての中間成果物は ~/.cache/security-agent/ 以下に保存し、GitHub Actions では actions/upload-artifact / actions/download-artifact でアーティファクトとして管理します。

~/.cache/security-agent/
└── benchmarks/
    ├── primevul/
    │   └── primevul_test_paired.jsonl        # Step 1: データセット
    ├── cvefixes/
    │   └── CVEfixes.db                       # Step 1: CVEfixes DB
    ├── vul4j/
    │   └── vul4j_export.jsonl                # Step 1: Vul4J エクスポート
    └── results/
        └── {dataset}/
            ├── semgrep_results.json          # Step 2: 静的ツール結果
            ├── codeql_results.jsonl          # Step 2: 静的ツール結果
            ├── llm_baseline_results.jsonl    # Step 2: LLMベースライン結果
            ├── static_baseline_results.jsonl # Step 2: 静的ベースライン結果
            ├── security_agent_results.jsonl  # Step 3: security-agent結果
            ├── evaluation_summary.json       # Step 4: 評価サマリー
            ├── metrics.json                  # Step 4: 詳細メトリクス
            └── report.md                     # Step 4: 可視化レポート
2. 現状の実装状況
2.1 実装済みのコンポーネント
以下のコンポーネントはコードとして実装されていますが、動作確認は未実施です。

benchmarks/datasets/builders/setup_benchmark.py: PrimeVul のダウンロードとキャッシュ
benchmarks/datasets/fetch_cvefixes.sh: CVEfixes DB のダウンロードとキャッシュ
benchmarks/datasets/fetch_vul4j.sh: Vul4J のダウンロードとキャッシュ
benchmarks/runners/run_semgrep.py: Semgrep の実行（Dockerコンテナ経由）
benchmarks/runners/run_codeql.py: CodeQL の実行（デフォルトモードとコマンドテンプレートモード）
benchmarks/runners/run_llm_baseline.py: Claude CLI 経由の LLM ベースライン
benchmarks/runners/run_static_baseline.py: Infer のデフォルト実行
benchmarks/rq2/evaluate.py: 全ツール結果の統合評価
benchmarks/rq2/generate_report.py: Markdown レポート生成
.github/workflows/benchmark-rq2-01-setup.yml: データセット準備ワークフロー
.github/workflows/benchmark-rq2-02-tools.yml: ツール実行ワークフロー
.github/workflows/benchmark-rq2-03-evaluate.yml: 評価ワークフロー
2.2 未実装・要修正の箇所
箇所	現状	必要な対応
run_security_agent.py	--command 未指定時は runner_not_configured エラーを返すのみ	security-agent 本体の呼び出しロジックを実装する
benchmark-rq2-02-tools.yml の security_agent ステップ	"security_agent is not implemented; skipping." とハードコードされてスキップ	実装後に有効化する
結果のキャッシュ（GitHub Actions）	Gitブランチへのコミットで管理	actions/upload-artifact / actions/download-artifact に移行する
evaluate.py の bootstrap_metric_diffs 呼び出し	samples, seed, ci_level 引数が不足している可能性あり	関数シグネチャとの整合性を確認する
3. 進め方：ステップ別実行手順
Step 1: データセット取得の動作確認とキャッシュ整備
3.1.1 動作確認
まず、PrimeVul データセットの取得スクリプトが正常に動作することを確認します。

# ローカルでの動作確認
cd /path/to/security-agent
uv sync --python 3.11
uv run python benchmarks/datasets/builders/setup_benchmark.py
正常に完了すると、以下のファイルが生成されます。

benchmarks/data/primevul/primevul_test_paired.jsonl（リポジトリ内）
~/.cache/security-agent/benchmarks/primevul/primevul_test_paired.jsonl（キャッシュ）
確認コマンド:

# ファイルが存在し、JSONL形式として正しく読めることを確認
head -n 1 benchmarks/data/primevul/primevul_test_paired.jsonl | python3 -m json.tool
wc -l benchmarks/data/primevul/primevul_test_paired.jsonl
3.1.2 GitHub Workflow への Artifact 保存の追加
benchmark-rq2-01-setup.yml の末尾に以下のステップを追加します。

      - name: Cache Dataset to Artifact
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: rq2-dataset-${{ inputs.dataset }}-${{ github.run_id }}
          path: benchmarks/data/${{ inputs.dataset }}/
          retention-days: 30
          if-no-files-found: warn

      - name: Cache to ~/.cache
        run: |
          CACHE_DIR="${HOME}/.cache/security-agent/benchmarks/${{ inputs.dataset }}"
          mkdir -p "${CACHE_DIR}"
          cp -rf benchmarks/data/${{ inputs.dataset }}/. "${CACHE_DIR}/"
          echo "Cached to ${CACHE_DIR}"
3.1.3 後続ワークフローでの Artifact ダウンロード
benchmark-rq2-02-tools.yml の Setup Python (uv) ステップの前に以下を追加します。

      - name: Download Dataset Artifact
        uses: actions/download-artifact@v4
        with:
          name: rq2-dataset-${{ inputs.dataset }}-${{ inputs.dataset_run_id }}
          path: benchmarks/data/${{ inputs.dataset }}/
        continue-on-error: true  # キャッシュがない場合はGitから取得

      - name: Fallback to ~/.cache
        run: |
          CACHE_DIR="${HOME}/.cache/security-agent/benchmarks/${{ inputs.dataset }}"
          DEST_DIR="benchmarks/data/${{ inputs.dataset }}"
          if [ ! -f "${DEST_DIR}/"*.jsonl ] && [ -d "${CACHE_DIR}" ]; then
            echo "Restoring from ~/.cache..."
            mkdir -p "${DEST_DIR}"
            cp -rf "${CACHE_DIR}/." "${DEST_DIR}/"
          fi
注意: dataset_run_id はワークフロー入力パラメータとして追加し、Step 1 の実行 ID を指定できるようにします。あるいは、actions/cache アクションを使って自動的にキャッシュキーを管理する方法も検討してください。

Step 2: 静的ツールのベンチマーク実行とキャッシュ保存
3.2.1 Semgrep の動作確認
Semgrep は Docker コンテナ経由で実行されます。まず Docker イメージをビルドします。

# Dockerイメージのビルド
docker build -t security-agent-benchmark -f benchmarks/Dockerfile .

# 動作確認（少数サンプルで実行）
docker run --rm -v "$PWD":/app security-agent-benchmark \
  python3 /app/benchmarks/runners/run_semgrep.py \
    --dataset /app/benchmarks/data/primevul/primevul_test_paired.jsonl \
    --output /app/benchmarks/results/rq2/primevul/semgrep_results.json \
    --timeout 60
確認ポイント:

benchmarks/results/rq2/primevul/semgrep_results.json が生成されること
benchmarks/results/rq2/primevul/semgrep_metadata.json が生成されること
各レコードに func_id と semgrep_findings が含まれること
3.2.2 CodeQL の動作確認
CodeQL CLI がインストールされている環境で実行します。

# デフォルトモード（codeql CLIが必要）
uv run python benchmarks/runners/run_codeql.py \
  --dataset benchmarks/data/primevul/primevul_test_paired.jsonl \
  --output benchmarks/results/rq2/primevul/codeql_results.jsonl \
  --tmp-dir benchmarks/tmp/codeql \
  --timeout 120
3.2.3 LLM ベースラインの動作確認
# Claude CLIが必要
uv run python benchmarks/runners/run_llm_baseline.py \
  --dataset benchmarks/data/primevul/primevul_test_paired.jsonl \
  --output benchmarks/results/rq2/primevul/llm_baseline_results.jsonl \
  --tmp-dir benchmarks/tmp/llm_baseline \
  --timeout 60 \
  --limit 10  # まず10件でテスト
3.2.4 結果のキャッシュ保存
benchmark-rq2-02-tools.yml の末尾に以下を追加します。

      - name: Save Results to Cache
        if: always()
        run: |
          CACHE_DIR="${HOME}/.cache/security-agent/benchmarks/results/${{ inputs.dataset }}"
          mkdir -p "${CACHE_DIR}"
          if [ -d "benchmarks/results/rq2/${{ inputs.dataset }}" ]; then
            cp -rf "benchmarks/results/rq2/${{ inputs.dataset }}/." "${CACHE_DIR}/"
            echo "Saved results to ${CACHE_DIR}"
          fi

      - name: Upload Results Artifact
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: rq2-tool-results-${{ inputs.dataset }}-${{ inputs.tools }}-${{ github.run_id }}
          path: benchmarks/results/rq2/${{ inputs.dataset }}/
          retention-days: 30
          if-no-files-found: warn
Step 3: security-agent のベンチマーク実行
これは、現在security-agentのトークン消費量問題を解決中なので、一旦スキップでOKです。
ただし、このステップを実行するためには、脆弱性データセットとともに、対象OSSの仕様書を確認できるURLリンクが必要となります。それを取得する方法についても考えておいてください。
この後のStep4は、Step3のデータがなくても空の状態で進められるようにしておくとよいでしょう。

3.3.1 run_security_agent.py の実装方針
現状の run_security_agent.py は --command 引数にコマンドテンプレートを渡すことで動作します。テンプレートには以下のプレースホルダーが使用できます。

プレースホルダー	説明
{code_path}	解析対象コードファイルのパス
{output_path}	予測結果を書き込む JSON ファイルのパス
{case_id}	サンプルの ID
出力ファイル（{output_path}）には以下の形式の JSON を書き込む必要があります。

{
  "predicted_vulnerable": true,
  "confidence": 0.85,
  "findings": 2,
  "spec": "Buffer overflow detected in function foo at line 42."
}
predicted_vulnerable フィールドが必須で、true / false のブール値を返します。spec フィールドは任意ですが、ユニーク検出例の表示に使用されます。

3.3.2 security-agent 呼び出しスクリプトの作成
security-agent の監査ロジックを単一ファイルに対して実行するラッパースクリプトを作成します。

# benchmarks/runners/invoke_security_agent.sh の例
#!/usr/bin/env bash
set -euo pipefail

CODE_PATH="$1"
OUTPUT_PATH="$2"
CASE_ID="$3"

# security-agent の実行（実際のコマンドに置き換える）
# 例: python -m security_agent.cli audit --file "${CODE_PATH}" --output "${OUTPUT_PATH}"
# 出力形式: {"predicted_vulnerable": true/false, "confidence": 0.0-1.0}

echo '{"predicted_vulnerable": false, "error": "not_implemented"}' > "${OUTPUT_PATH}"
このスクリプトを --command 引数に渡します。

uv run python benchmarks/runners/run_security_agent.py \
  --dataset benchmarks/data/primevul/primevul_test_paired.jsonl \
  --output benchmarks/results/rq2/primevul/security_agent_results.jsonl \
  --tmp-dir benchmarks/tmp/security_agent \
  --command "bash benchmarks/runners/invoke_security_agent.sh {code_path} {output_path} {case_id}" \
  --shell \
  --timeout 300 \
  --limit 10  # まず10件でテスト
3.3.3 ワークフローへの統合
benchmark-rq2-02-tools.yml の Resolve Tool Selection ステップを修正し、security_agent を有効化します。

          if echo "$TOOLS" | grep -Eq "security_agent|agent"; then
            echo "run_security_agent=true" >> $GITHUB_OUTPUT  # falseからtrueに変更
          else
            echo "run_security_agent=false" >> $GITHUB_OUTPUT
          fi
Security Agent (not implemented) ステップを以下に置き換えます。

      - name: Run Security Agent
        if: steps.tool_select.outputs.run_security_agent == 'true'
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          if [ "${{ inputs.force_execute }}" != "true" ] && \
             [ -f "${RESULTS_DIR}/security_agent_results.jsonl" ]; then
            echo "Security agent results already exist. Use force_execute to re-run."
            exit 0
          fi
          uv run python benchmarks/runners/run_security_agent.py \
            --dataset "${DATASET_PATH}" \
            --output "${RESULTS_DIR}/security_agent_results.jsonl" \
            --tmp-dir benchmarks/tmp/security_agent \
            --command "${{ inputs.security_agent_command }}" \
            --shell \
            --timeout "${{ inputs.tool_timeout }}"
また、workflow_dispatch の inputs に security_agent_command を追加します。

      security_agent_command:
        description: "security-agent command template ({code_path}, {output_path}, {case_id})"
        required: false
        type: string
        default: ""
Step 4: 評価と結果の可視化
3.4.1 評価の実行
benchmark-rq2-03-evaluate.yml を実行します。このワークフローは、前のステップで生成された結果ファイルを基に評価を行います。

# ローカルでの実行例
uv run python benchmarks/rq2/evaluate.py \
  --dataset primevul \
  --dataset-path benchmarks/data/primevul/primevul_test_paired.jsonl
生成される出力ファイル:

benchmarks/results/rq2/evaluation_summary.json: 全ツールの評価サマリー
benchmarks/results/rq2/metrics.json: 詳細なメトリクス（CWEカバレッジ、ペアワイズ統計など）
3.4.2 レポート生成の自動化
benchmark-rq2-03-evaluate.yml に以下のステップを追加します。

      - name: Generate Report
        run: |
          uv run python benchmarks/rq2/generate_report.py \
            --metrics benchmarks/results/rq2/metrics.json \
            --output benchmarks/results/rq2/report.md

      - name: Upload Evaluation Artifacts
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: rq2-evaluation-${{ inputs.dataset }}-${{ github.run_id }}
          path: |
            benchmarks/results/rq2/evaluation_summary.json
            benchmarks/results/rq2/metrics.json
            benchmarks/results/rq2/report.md
          retention-days: 90

      - name: Save Evaluation to ~/.cache
        if: always()
        run: |
          CACHE_DIR="${HOME}/.cache/security-agent/benchmarks/results/${{ inputs.dataset }}"
          mkdir -p "${CACHE_DIR}"
          for f in evaluation_summary.json metrics.json report.md; do
            if [ -f "benchmarks/results/rq2/${f}" ]; then
              cp "benchmarks/results/rq2/${f}" "${CACHE_DIR}/${f}"
            fi
          done
          echo "Saved evaluation results to ${CACHE_DIR}"

      - name: Print Report Summary
        run: |
          echo "## RQ2 Benchmark Report" >> $GITHUB_STEP_SUMMARY
          cat benchmarks/results/rq2/report.md >> $GITHUB_STEP_SUMMARY
Step 5: 再実験のフロー
各ステップは独立して再実行可能です。以下のフローで必要な部分だけを再実験できます。

[Step 1] データセット取得
    ↓ (キャッシュあり → スキップ可)
[Step 2] 静的ツール実行 (semgrep, codeql, llm, static)
    ↓ (force_execute: false → 既存結果を使用)
[Step 3] security-agent 実行
    ↓ (force_execute: true → 強制再実行)
[Step 4] 評価・レポート生成
    ↓
[完了] report.md をアーティファクトとして確認
security-agent のみ再実行する場合:

benchmark-rq2-02-tools.yml を以下のパラメータで実行します。

tools: security_agent
force_execute: true
security_agent_command: 新しいコマンドテンプレート
完了後、benchmark-rq2-03-evaluate.yml を実行して評価を更新します。

キャッシュを活用した部分再実行:

self-hostedランナー上の ~/.cache/security-agent/benchmarks/results/{dataset}/ には、過去の実行結果が保存されています。特定のツールの結果のみを削除して再実行することで、他のツールの結果を再利用しながら効率的に再実験できます。

# security-agent の結果のみ削除して再実行する例（ランナーホストで実行）
rm ~/.cache/security-agent/benchmarks/results/primevul/security_agent_results.jsonl
# その後、benchmark-rq2-02-tools.yml を tools: security_agent で実行
4. GitHub Workflow 全体設計
4.1 ワークフロー一覧と依存関係
benchmark-rq2-01-setup.yml
    │
    │ (Artifact: rq2-dataset-{dataset}-{run_id})
    ▼
benchmark-rq2-02-tools.yml
    │
    │ (Artifact: rq2-tool-results-{dataset}-{tools}-{run_id})
    ▼
benchmark-rq2-03-evaluate.yml
    │
    │ (Artifact: rq2-evaluation-{dataset}-{run_id})
    ▼
  report.md (GitHub Step Summary に表示)
4.2 各ワークフローの修正方針
benchmark-rq2-01-setup.yml の修正点
追加: actions/upload-artifact でデータセットをアーティファクトとして保存
追加: ~/.cache/security-agent/benchmarks/ へのキャッシュ保存ステップ
変更: Gitブランチへのコミット・プッシュは廃止（アーティファクトに移行）
benchmark-rq2-02-tools.yml の修正点
追加: actions/download-artifact でデータセットアーティファクトを取得
追加: ~/.cache からのフォールバック取得ステップ
修正: security_agent の実行ステップを有効化
追加: security_agent_command 入力パラメータ
追加: 結果を actions/upload-artifact で保存
追加: ~/.cache/security-agent/benchmarks/results/ へのキャッシュ保存ステップ
変更: Gitブランチへのコミット・プッシュは廃止
benchmark-rq2-03-evaluate.yml の修正点
追加: actions/download-artifact でツール結果アーティファクトを取得
追加: ~/.cache からのフォールバック取得ステップ
追加: generate_report.py の実行ステップ
追加: 評価結果を actions/upload-artifact で保存
追加: ~/.cache への保存ステップ
追加: $GITHUB_STEP_SUMMARY へのレポート出力
変更: Gitブランチへのコミット・プッシュは廃止
4.3 self-hosted ランナーの要件
すべてのワークフローは runs-on: self-hosted で実行されます。ランナーホストには以下のツールが必要です。

ツール	用途	インストール方法
Docker	Semgrep の実行	apt-get install docker.io
CodeQL CLI	CodeQL の実行	公式ドキュメント
uv	Python 環境管理	`curl -LsSf https://astral.sh/uv/install.sh
clang / clang++	CodeQL のビルド	apt-get install clang
sqlite3	CVEfixes DB の構築	apt-get install sqlite3
キャッシュを確認・修正したい場合は、ランナーホストに SSH 接続して ~/.cache/security-agent/ 以下を直接操作します。

5. 既知の問題と対処方針
5.1 evaluate.py の bootstrap_metric_diffs 呼び出し
benchmarks/rq2/evaluate.py の bootstrap_metric_diffs 呼び出しで、samples, seed, ci_level 引数が不足している可能性があります。benchmarks/metrics/stats.py の関数シグネチャを確認し、必要に応じて修正します。

# stats.py の関数シグネチャ（要確認）
def bootstrap_metric_diffs(
    tool_a, tool_b, ground_truth, case_ids,
    samples: int,    # ← evaluate.py から渡されているか確認
    seed: int,       # ← evaluate.py から渡されているか確認
    ci_level: float, # ← evaluate.py から渡されているか確認
) -> dict: ...
5.2 PrimeVul の func_hash vs id の不整合
run_semgrep.py は func_hash をキーとして使用しますが、evaluate.py は id や func_hash など複数のキーを試みます。bench_utils.py の extract_id 関数が func_hash を含む ID_KEYS タプルを参照しているため、基本的には問題ありませんが、Semgrep の結果ファイルの func_id キーが evaluate.py の load_semgrep_results で正しく処理されることを確認してください。

5.3 security_agent の実行時間
PrimeVul の全件（数万件）に対して security-agent を実行すると、非常に長い時間がかかります。初期実験では --limit オプションで件数を制限し、段階的にスケールアップすることを推奨します。

6. ローカルでの一括実行スクリプト
デバッグや開発中の動作確認のために、以下のスクリプトを使用できます。

#!/usr/bin/env bash
# run_rq2_local.sh - RQ2ベンチマークのローカル実行スクリプト
set -euo pipefail

DATASET="${1:-primevul}"
TOOLS="${2:-semgrep}"  # semgrep, codeql, llm, static, security_agent, all
LIMIT="${3:-0}"        # 0 = 全件

echo "=== Step 1: Dataset Setup ==="
uv run python benchmarks/datasets/builders/setup_benchmark.py

echo "=== Step 2: Run Tools (${TOOLS}) ==="
DATASET_PATH="benchmarks/data/${DATASET}/${DATASET}_test_paired.jsonl"
RESULTS_DIR="benchmarks/results/rq2/${DATASET}"
mkdir -p "${RESULTS_DIR}"

if [[ "${TOOLS}" == "all" || "${TOOLS}" == *"semgrep"* ]]; then
  docker build -t security-agent-benchmark -f benchmarks/Dockerfile . -q
  docker run --rm -v "$PWD":/app security-agent-benchmark \
    python3 /app/benchmarks/runners/run_semgrep.py \
      --dataset "/app/${DATASET_PATH}" \
      --output "/app/${RESULTS_DIR}/semgrep_results.json" \
      --timeout 60
fi

if [[ "${TOOLS}" == "all" || "${TOOLS}" == *"codeql"* ]]; then
  uv run python benchmarks/runners/run_codeql.py \
    --dataset "${DATASET_PATH}" \
    --output "${RESULTS_DIR}/codeql_results.jsonl" \
    --tmp-dir benchmarks/tmp/codeql \
    --timeout 120 \
    ${LIMIT:+--limit ${LIMIT}}
fi

echo "=== Step 3: Evaluate ==="
uv run python benchmarks/rq2/evaluate.py \
  --dataset "${DATASET}" \
  --dataset-path "${DATASET_PATH}"

echo "=== Step 4: Generate Report ==="
uv run python benchmarks/rq2/generate_report.py \
  --metrics benchmarks/results/rq2/metrics.json \
  --output benchmarks/results/rq2/report.md

echo "=== Done ==="
echo "Report: benchmarks/results/rq2/report.md"
7. 参考リンク
benchmarks/README.md: RQ1/RQ2 の概要と実行方法
benchmarks/rq2/evaluate.py: 評価ロジックの実装
benchmarks/rq2/generate_report.py: レポート生成の実装
benchmarks/runners/base_runner.py: ランナー共通ヘルパー
benchmarks/tools/registry.py: ツールレジストリ（結果ファイルのパス解決）
benchmarks/metrics/classification.py: 分類指標の計算
benchmarks/metrics/stats.py: 統計検定・ブートストラップ CI