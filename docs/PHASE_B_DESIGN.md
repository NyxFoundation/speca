# Phase B — Prompt Self-Improvement Design

> **ステータス:** Draft — issue #2 W4–W7 向け設計文書  
> **対象ブランチ:** `docs/phase-b-design`  
> **前提:** Phase A コード (PR #51, `9bc4da29`) が `main` にマージ済み

---

## 0. ステータス・スコープ・非対象事項

### スコープ (W4–W7 成果物)

- Per-phase eval ハーネス構築 — `introduced_in_commit` タイムスライス replay
- Per-phase プロンプト反復最適化 — 最大 6 ラウンド × フェーズあたり $300 上限
- 全イテレーションでの cross-client 汎化チェック
- Acceptance gate B — `prompts/eth-audit-2026/locked/` タグ付け + held-out スライスで recall +10 pp 以上

### 非対象事項 (明示的に後回し)

- RL ベースのファインチューニング (モデル重みの更新は行わない)
- マルチモデルアンサンブル
- Phase C (11 クライアント全量 audit run) の実行そのもの
- `ISSUE#` / `CHANGELOG#` ソース行の `introduced_in_commit` 解決 (`blame_walk.py` の TODO 参照)

### Acceptance gate B (再掲)

```
locked tag prompts/eth-audit-2026/locked/ が存在し、
held-out 100 レコードスライスで recall ≥ baseline + 10 pp
```

---

## 1. 背景 — 文献が示すこと

### 1.1 文献一覧

#### [1] APE: Large Language Models Are Human-Level Prompt Engineers
- **arXiv:** 2211.01910 (2022)
- **著者:** Zhou et al.
- **概要:** プロンプト最適化を black-box 自然言語最適化問題として定式化。LLM が候補命令を生成し、評価セット上のスコアで選別する。蒙テカルロ探索で最良候補を意味的に近傍変異させるイテレーションループを採用。24 NLP タスク中 19 でヒューマンアノテーター作成プロンプトに匹敵または上回る性能を達成。
- **speca が借用すべき点:** ラウンドごとに「スコア付き候補プール → 上位候補を変異 → 再評価」というイテレーション骨格。評価スコアは speca では held-out recall に置き換える。

#### [2] OPRO: Large Language Models as Optimizers
- **arXiv:** 2309.03409 (2023)
- **著者:** Yang et al. (Google DeepMind)
- **概要:** 「最適化タスクを自然言語で記述し、LLM が過去の解とそのスコアを見て次の解を提案する」という OPRO フレームワーク。過去スコア付き解の列をプロンプトに付加し、数値フィードバックを言語的文脈として利用。GSM8K で人手設計プロンプトより最大 8 pp 向上。
- **speca が借用すべき点:** スコア履歴をプロポーザーに渡すことで単純なランダム変異より効率的に良いプロンプトを探索する構造。コスト記録 (`CostTracker.get_history()`) をそのままコンテキストとして再利用できる。

#### [3] Reflexion: Language Agents with Verbal Reinforcement Learning (NeurIPS 2023)
- **arXiv:** 2303.11366 (2023)
- **著者:** Shinn et al.
- **概要:** 環境からのバイナリ/スカラー報酬をテキストの "reflection" に変換し、エピソードメモリに蓄積する。次エピソードでエージェントはこの verbal feedback を参照して行動を改善。重み更新なしで AlfWorld +22%, HumanEval 91% pass@1 を達成。
- **speca が借用すべき点:** 「eval ハーネスが recall スコアを返す → proposer が誤検知・見逃しをテキストで分析して次ラウンドのプロンプト改訂案を生成する」という反省ループ。これが Phase B の中核アルゴリズムとなる。

#### [4] Self-Refine: Iterative Refinement with Self-Feedback (NeurIPS 2023)
- **arXiv:** 2303.17651 (2023)
- **著者:** Madaan et al.
- **概要:** 単一 LLM を generator・feedback provider・refiner の三役で使う。追加学習・RL 不要。コード生成タスクで CODEX ベースラインより最大 13 pp 向上。7 タスク平均で約 20 pp の絶対改善。
- **speca が借用すべき点:** 同一モデルを proposer と evaluator に使える (speca では Sonnet が両役を担う) ことの先例。フィードバックは eval ハーネスの誤検知リストという形で外部化するので、自己バイアスは緩和できる。

#### [5] DSPy: Compiling Declarative Language Model Calls into Self-Improving Pipelines (ICLR 2024)
- **arXiv:** 2310.03714 (2023)
- **著者:** Khattab et al. (Stanford)
- **概要:** LLM パイプラインをパラメータ化モジュールのグラフとして抽象化し、コンパイラが任意のメトリクスを最大化するようプロンプトを最適化する。BootstrapFewShot オプティマイザは合格デモを自動収集してプロンプトに埋め込む。GPT-3.5 で human-designed baseline を 25 % 以上上回る。
- **speca が借用すべき点:** 検証セット上の recall を最大化する方向で「合格サンプル (true positive)」を few-shot 例としてプロンプトに自動挿入する手法。speca の held-out true positives を few-shot 候補として使える。

#### [6] EvoPrompt: Connecting LLMs with Evolutionary Algorithms Yields Powerful Prompt Optimizers (ICLR 2024)
- **arXiv:** 2309.08532 (2023)
- **著者:** Guo et al.
- **概要:** 遺伝的アルゴリズム (GA) と差分進化 (DE) を LLM の自然言語生成能力と組み合わせ、プロンプト集団を進化させる。31 データセットで既存手法より最大 25 pp 向上。勾配もパラメータも不要。
- **speca が借用すべき点:** 6 ラウンドという少ない反復で探索効率を高めるために、GA 的な交叉 (2 つのプロンプト候補を LLM に渡して合成させる) を 3 ラウンド以降に取り入れる選択肢。ただし実装コストが増すため、まず Reflexion スタイルの単純変異で試す (§3.3 参照)。

#### [7] PromptBreeder: Self-Referential Self-Improvement Via Prompt Evolution (2023)
- **arXiv:** 2309.16797 (2023)
- **著者:** Fernando et al. (DeepMind)
- **概要:** タスクプロンプトだけでなく「変異プロンプト」自体も LLM が進化させる自己参照ループ。Chain-of-Thought・Plan-and-Solve を arithmetic/reasoning ベンチマークで上回る。ヘイトスピーチ分類という難問にも適用。
- **speca が借用すべき点:** 変異戦略 (mutation-prompt) をも最適化するアイデア。ただし 6 ラウンドの予算では二重最適化は過剰なため、変異プロンプトは固定し audit フェーズプロンプトのみを対象とする。

#### [8] LLMs in Software Security: A Survey of Vulnerability Detection Techniques and Insights
- **arXiv:** 2502.07049 (2025)
- **著者:** Sheng et al.
- **概要:** 2019–2024 年の 80 本超を体系的サーベイ。LLM による脆弱性検出において CoT プロンプティングが複雑なコード推論を有意に改善することを確認。関数レベル・ファイルレベルのデータセットが多くリポジトリレベルの評価が不足していることを指摘。
- **speca が借用すべき点:** Phase B の eval ハーネスでリポジトリレベルの replay を行うことの正当性。また CoT 形式を Phase 03/04 プロンプト改善の変異方向として優先すべきという示唆。

#### [9] iAudit: Combining Fine-Tuning and LLM-based Agents for Intuitive Smart Contract Auditing with Justifications
- **arXiv:** 2403.16073 (2024)
- **著者:** Ma et al.
- **概要:** Fine-tuned Reasoner + Ranker/Critic エージェントの二段構成でスマートコントラクト監査を行う。Ranker と Critic が反復的なデベートで脆弱性の根拠を選択・洗練し、F1 91.21% を達成。
- **speca が借用すべき点:** 「ランカー (評価モデル) が外部から判定を返し、proposer がそのフィードバックで改訂する」という分離構造。speca の eval ハーネスがランカー役を担い、Sonnet が proposer 役を担う形と対応する。

#### [10] A Systematic Survey of Automatic Prompt Optimization Techniques
- **arXiv:** 2502.16923 (2025)
- **著者:** Ramnath et al.
- **概要:** APO (Automatic Prompt Optimization) を 5 コンポーネントフレームワークで体系化。主要手法 (OPRO, EvoPrompt GA/DE, CAPO) を比較整理し、held-out 評価なしでは外部汎化が保証されないと明示。
- **speca が借用すべき点:** Phase B において train/validation/test の 3 分割を厳守し、最適化ループ内では validation のみ触る設計の根拠。

### 1.2 文献が収束する点

1. **反省ループ (Critique loop):** 誤り・見逃しのテキスト分析を次ラウンドのプロンプト改訂に使う手法が最もシンプルで一貫して有効 (Reflexion [3], Self-Refine [4], iAudit [9])。コード分析領域では特に「なぜこのケースを見逃したか」というテキスト診断が次プロンプトの特定箇所の改訂につながりやすい。
2. **数値スコア履歴のコンテキスト化:** 過去ラウンドのスコアをプロポーザーに渡すことで単純ランダム変異より効率的に探索が進む (OPRO [2])。speca では `CostTracker.get_history()` が返す per-batch コスト履歴と合わせて、「このラウンドでいくら使ってどれだけ recall が上がったか」をプロポーザーコンテキストに含められる。
3. **外部評価セットの必須化:** held-out 検証なしでは過学習リスクが排除できない (APO survey [10])。最適化ループ内で触るのは validation slice のみとし、test は acceptance gate 判定時のみ使う 3 分割が推奨される。
4. **変異は small step が安全:** 大規模変異 (EvoPrompt GA/DE [6]) は少ないラウンドでは各ラウンドの候補評価コストが高くなり、$50/ラウンド の予算制約に合わない。小さな単一ラインの改訂 + 反省ループの組み合わせが 6 ラウンド程度の予算で費用対効果が高い。EvoPrompt 的な交叉は停滞時の fallback として 3 ラウンド以降に限定して試みる。
5. **脆弱性検出ドメインでの有効性:** LLM によるスマートコントラクト audit では well-designed prompt が FP 率を 60% 超削減することが実証されており (SmartGuard 等)、プロンプト改善の余地は大きい [8]。CoT 形式が複雑なコード推論を有意に改善する点はサーベイ [8] が繰り返し確認している。

### 1.3 未解決・意見が分かれる点

- **提案モデルと評価モデルを分けるべきか:** Self-Refine [4] は同一モデルで代用できると主張するが、iAudit [9] は Ranker/Critic を分離することで議論の質が上がると主張する。speca では eval ハーネスが固定スクリプトで recall を算出するため自己評価バイアスの問題は回避できる。ただし critique 生成を同一 Sonnet に任せると、プロポーザーが自分のプロンプトへの改訂を過大評価するリスクは残る。
- **Few-shot 例挿入の効果:** DSPy [5] は BootstrapFewShot による true positive 挿入が有効と示すが、Phase 03 では `max_context_tokens=120,000` という制約があり、few-shot 例を多数挿入するとワーカーが読む対象コードの分量が減る。挿入する場合は 2–3 例に制限し、examples フィールドを分離管理する。
- **Cross-distribution 汎化の検証方法:** 既存研究のほとんどは単一 distribution (単一言語・単一フレームワーク) で評価しており、11 Ethereum クライアント間のプロンプト転移性について先行研究の直接的なエビデンスはない。Phase B では実験的に確認するしかない。
- **`introduced_in_commit` 解決率の不確実性:** `blame_walk.py` の設計では ISSUE#/CHANGELOG# ソース行は常に `""` となる (同ファイル L17-L19 の TODO)。Phase A 完成後に有効レコードが 100 件を割る場合の fallback 戦略は open question (§8 Q3)。

---

## 2. Speca 固有のフレーミング

### 2.1 最適化対象プロンプト

パイプラインの各フェーズに対応するプロンプトファイルが最適化ターゲットとなる:

| フェーズ | プロンプトファイル | 役割 | 優先度 |
|---|---|---|---|
| 01a | `prompts/01a_crawl.md` | スペック発見 | 低 (スキルfork) |
| 01b | `prompts/01b_extract_worker.md` | サブグラフ抽出 | 低 (スキルfork) |
| 01e | `prompts/01e_prop_worker.md` | プロパティ生成 | 高 |
| 02c | `prompts/02c_codelocation_worker.md` | コードロケーション | 中 |
| 03 | `prompts/03_auditmap_worker_inline.md` | Audit Map 生成 | 最高 |
| 04 | `prompts/04_review_worker.md` | FP フィルタ | 高 |

フェーズ 01a/01b はスキルフォーク形式かつ recall への直接影響が小さいため最後に対応する。フェーズ 03 は $200 budget (最も高い) かつ recall への影響が最大であるため最初のターゲットとする。

### 2.2 Phase A データセットをシグナルとして使う

Phase A が生成した `benchmarks/data/ethereum_past_fixes/` の CSV と `dist/datasets/ethereum/train.parquet` が Phase B の supervision signal となる。重要フィールド:

- `introduced_in_commit` — `blame_walk.py` が解決した脆弱性導入コミット (= fix commit の parent)
- `stride`, `cwe_top25` — `classify_stride_cwe.py` が付与したラベル
- `source_platform` — クライアント識別子 (cross-client 分割に使用)
- `severity` — eval 時のフィルタリング

**replay の意味論:** `introduced_in_commit` 時点のコードベースに Phase 03/04 プロンプトを適用し、「この過去修正が検出できるか」を問う。この意味論は `blame_walk.py` の設計ドキュメント (L1-L11) が明示している通り、`introduced_in_commit` は fix commit の parent (= 脆弱な状態の最新コミット) を指すため、「壊れたコードベースを audit して検出できるか」という replay 意味論と一致する。`introduced_in_commit` が空のレコード (ISSUE#/CHANGELOG# ソース) は replay から除外する。

### 2.3 評価メトリクスの定義

```
recall@held-out = (held-out スライスで検出できた true positive 数) / (held-out スライスの全 true positive 数)
```

「検出」の定義: Phase 04 出力が `CONFIRMED_VULNERABILITY` または `CONFIRMED_POTENTIAL` で、かつ対応する held-out レコードにトレースできる場合 (トレーサビリティの詳細は §3.1 および §8 Q5 参照)。

**注意: precision は今ラウンドでは計測しない。** Phase 04 の recall-safe 設計 (`scripts/CLAUDE.md:L56-L58` に記述のある 3-gate FP フィルタ) の趣旨を壊さないため、FP の増加はスコアに反映せず、Phase C acceptance gate (`precision ≥ 50%` per client) で別途管理する。

**held-out スライスの構成:** 100 レコード。STRIDE × severity × source_platform (クライアント) のストラトファイド抽出。seed=42 固定。全ラウンドで同一スライスを使用する (ラウンドごとの再抽出については §8 Q1 および §6.1 参照)。

**baseline の定義:** Phase B 開始前に現行の `prompts/03_auditmap_worker_inline.md` および `prompts/04_review_worker.md` を使って同じ held-out スライスで recall を計測した値。この baseline 計測自体もコストが発生するため `CostTracker` でカウントし、フェーズあたり $300 の cap に含める。

---

## 3. アーキテクチャ

### 3.1 Eval ハーネス (新規: `scripts/prompt_loop/eval_harness.py`)

```
EvalHarness
  .load_held_out_slice(parquet_path, n=100, seed=42) -> HeldOutSlice
  .replay_phase(phase_id, prompt_path, slice, client_clone_root) -> EvalResult
  .score(eval_result) -> RecallScore
```

**動作フロー:**

1. `scripts/datasets/load.py:load_findings()` で `ethereum` ドメインを読み込む
2. `introduced_in_commit != ""` の行のみ保持し、STRIDE × severity × source_platform のストラトファイド抽出で 100 レコードの `HeldOutSlice` を構成 (seed=42 固定)
3. 各レコードに対して、対応クライアントリポジトリを `introduced_in_commit` SHA でチェックアウト。チェックアウト先は `client_clone_root/<source_platform>/` 以下の bare clone + worktree 形式を推奨 (ディスク節約)
4. `outputs/TARGET_INFO.json` を一時的に `introduced_in_commit` SHA で上書きし、Phase 01a → 04 のうち評価対象フェーズの replay を `ClaudeRunner.run_batch()` (`scripts/orchestrator/runner.py:L291`) で実行
5. Phase 04 出力 (`04_PARTIAL_*.json`) を読み取り、`review_verdict` が `CONFIRMED_VULNERABILITY` または `CONFIRMED_POTENTIAL` のアイテムのうち、held-out レコードにトレースできるものを TP としてカウントし recall を算出

**既存コードの流用:** `BaseOrchestrator.run()` のバッチ実行フロー (`scripts/orchestrator/base.py:L185-L301`) を参考に同様の async ループを実装する。`PhaseConfig` を改変して eval ハーネス専用の一時設定 (workdir, output_pattern 等) を注入する。`CostTracker` を注入して eval 実行コストもカウントする。`SPECA_OUTPUT_DIR` 環境変数 (`scripts/run_phase.py:L462-L463`) を利用してメインの `outputs/` と eval 用の一時ディレクトリを分離する。

**コスト管理:** eval 1 回あたりのコストを `CostTracker(max_budget_usd=50.0)` で計測し、`BudgetExceeded` が raise されたら eval を中断して最後に保存された partial 結果から recall を算出する。ラウンドレベルの $50 cap は `PromptOptimizer` が管理し、フェーズレベルの $300 cap は別の `CostTracker(max_budget_usd=300.0)` で独立して追跡する。

**TP トレーサビリティ:** held-out レコードの `issue_id` と Phase 03/04 出力の `property_id` を突き合わせる直接的な ID マッピングは存在しない。このため、`introduced_in_commit` コミットで replay した Phase 01e が生成する property のうち、held-out レコードの `stride` / `cwe_top25` ラベルと一致する property を「対応プロパティ」とみなし、Phase 04 でそれが検出されたかを recall の分子に加算する。マッチングロジックは `EvalHarness.score()` で `stride` 完全一致 + `cwe_top25` 完全一致 (or N/A の場合は stride のみ) で行う。この近似マッチングの精度は §8 Q5 として open question とする。

### 3.2 イテレーションループ (新規: `scripts/prompt_loop/optimizer.py`)

**採用アルゴリズム: Reflexion スタイルの critique ループ (§1.2 の収束点を根拠とする)**

OPRO の数値スコア履歴コンテキストと Reflexion の verbal critique を組み合わせた以下のパターンを採用する:

```
for round in range(max_rounds):  # max_rounds = 6
    eval_result = harness.replay_phase(phase_id, current_prompt, held_out)
    recall = harness.score(eval_result)

    if recall >= baseline_recall + 0.10:
        lock_prompt(current_prompt, round, recall)
        break

    # Proposer: Sonnet に critique + 改訂案を依頼
    critique = proposer.generate_critique(
        current_prompt=current_prompt,
        false_negatives=eval_result.false_negatives,  # 見逃したレコード
        false_positives=eval_result.false_positives,
        score_history=score_history,  # OPRO スタイル
    )
    candidate_prompts = proposer.propose(critique, n=3)

    # Selector: eval ハーネスで各候補を評価し最高 recall を選択
    best = max(candidate_prompts, key=lambda p: harness.score(harness.replay_phase(phase_id, p, held_out)))
    current_prompt = best
    score_history.append((round, best, recall))
```

**EvoPrompt 式変異を採用しない理由:** 6 ラウンドの予算では集団ベースの GA/DE 探索は各ラウンドの評価コストが高くなりすぎる。Reflexion スタイルの単一ラインの改訂 + verbal critique の方が per-round コストを抑えられる。EvoPrompt 的な交叉は 4 ラウンド以降でスコアが停滞した場合のみ fallback として試みる。

**クラス設計:**

```python
# scripts/prompt_loop/optimizer.py

class PromptProposer:
    """Sonnet を使って critique と改訂候補を生成する"""
    def __init__(self, runner: ClaudeRunner): ...
    def generate_critique(self, current_prompt, false_negatives, score_history) -> str: ...
    def propose(self, critique: str, n: int = 3) -> list[str]: ...

class PromptSelector:
    """候補プロンプトを eval ハーネスで採点し最良を返す"""
    def select(self, candidates, harness, phase_id, held_out) -> tuple[str, float]: ...

class PromptOptimizer:
    """ループ全体を管理する。コスト追跡・ラウンド管理・ロック判定を担う"""
    def __init__(self, phase_id, max_rounds=6, budget_per_round=50.0): ...
    def run(self, baseline_prompt_path, held_out_slice) -> OptimizeResult: ...
```

### 3.3 Cross-client 汎化ゲート (各ラウンドで実行)

**実装場所:** `scripts/prompt_loop/generalization_check.py`

各ラウンドで best candidate を選択した後、held-out スライスを `source_platform` (client_slug) で分割し、各クライアントについて recall を計算する:

```python
def cross_client_check(
    prompt_path: str,
    held_out: HeldOutSlice,
    harness: EvalHarness,
) -> dict[str, float]:
    """クライアントごとの recall を返す。
    あるクライアントで baseline より -5 pp 以上の回帰があれば警告を出す。"""
    by_client = {}
    for client_slug in held_out.client_slugs:
        client_slice = held_out.filter_by_client(client_slug)
        score = harness.score(harness.replay_phase(prompt_path, client_slice))
        by_client[client_slug] = score
    return by_client
```

**Phase A データ:** `source_platform` フィールドに 11 クライアントの識別子 (geth, nethermind, besu, erigon, reth, lighthouse, lodestar, nimbus, prysm, teku, grandine) が格納される。ただし 100 レコードを 11 分割すると平均 9 レコード/クライアントとなり統計的ノイズが高い。クライアント別 recall はトレンド把握のためのガイドラインとして使い、Hard gate (ラウンドブロック) ではなく Soft gate (警告) とする。

**判断:** この点は §8 の open question として明示する。

### 3.4 コストガード

`scripts/orchestrator/watchdog.py:CostTracker` と `BudgetExceeded` をそのまま使う:

```python
# scripts/prompt_loop/optimizer.py 内

cost_tracker = CostTracker(max_budget_usd=budget_per_round)  # $50/round
# ClaudeRunner に注入済みのため eval replay でも自動計測される

# ループ開始前に per-phase 累計コストも追跡
phase_cost_tracker = CostTracker(max_budget_usd=300.0)
```

`BudgetExceeded` が raise された場合、現時点で最高 recall のプロンプトを保存してループを終了する。6 ラウンド × $50 = $300 の上限は `PhaseConfig.max_budget_usd = 300.0` として `PHASE_CONFIGS` に Phase B 専用エントリを追加する必要はなく、`PromptOptimizer` 内部の `CostTracker` で管理する。

### 3.5 リポジトリ内の配置

```
scripts/
  prompt_loop/                  # 新規パッケージ
    __init__.py
    eval_harness.py             # HeldOutSlice, EvalHarness, EvalResult, RecallScore
    optimizer.py                # PromptProposer, PromptSelector, PromptOptimizer
    generalization_check.py     # cross_client_check()
    provenance.py               # ProvenanceManifest (§4 参照)
    cli.py                      # speca prompt-loop サブコマンドの実装本体 (§5)

tests/
  test_prompt_loop_harness.py   # eval ハーネスのユニットテスト
  test_prompt_loop_optimizer.py # optimizer ループのモックテスト
  test_prompt_loop_generalization.py
```

**既存 `scripts/orchestrator/` へは変更を加えない。** `ClaudeRunner` と `CostTracker` は import して使用するのみ。

---

## 4. Locked-prompt アーティファクト

### 4.1 ディレクトリレイアウト

```
prompts/
  eth-audit-2026/
    locked/
      03/
        v1.md          # Phase 03 の locked プロンプト
        manifest.json  # プロバナンス
      04/
        v1.md
        manifest.json
      01e/
        v1.md
        manifest.json
      02c/
        v1.md
        manifest.json
    post-mortem-2026.md   # Phase D 後に追記
```

### 4.2 Provenance マニフェスト形式

`manifest.json` には以下を記録する:

```json
{
  "phase_id": "03",
  "prompt_version": "v1",
  "locked_at": "2026-05-20T12:34:56Z",
  "speca_commit": "9bc4da29...",
  "phase_a_dataset_hash": "sha256:abcdef...",
  "held_out_slice_seed": 42,
  "held_out_n": 100,
  "baseline_recall": 0.47,
  "locked_recall": 0.61,
  "recall_delta_pp": 14.0,
  "rounds_used": 4,
  "total_cost_usd": 189.32,
  "client_recall": {
    "geth": 0.63,
    "nethermind": 0.58,
    "lighthouse": 0.60
  },
  "eval_date": "2026-05-20"
}
```

`scripts/prompt_loop/provenance.py:ProvenanceManifest` がこのスキーマを Pydantic モデルとして定義し、`PromptOptimizer.run()` の終了時に書き出す。

### 4.3 runtime での baseline / locked 切り替え

`scripts/orchestrator/config.py:PhaseConfig` に `prompt_override_path: Path | None = None` フィールドを追加する:

```python
# config.py への追加 (既存フィールドに影響しない)
prompt_override_path: Path | None = None
```

`scripts/run_phase.py:run_phase()` に `--locked` フラグを追加し、指定された場合は:

```python
if args.locked:
    locked_path = Path(f"prompts/eth-audit-2026/locked/{phase_id}/v1.md")
    if locked_path.exists():
        orchestrator.config.prompt_path = locked_path
```

で `PhaseConfig.prompt_path` を上書きする。これにより既存の `ClaudeRunner._build_prompt()` (`scripts/orchestrator/runner.py:L814`) がそのまま locked プロンプトを読み込む。

---

## 5. `speca-cli` との統合

### 5.1 新規サブコマンド

```
speca prompt-loop --phase 03 [--rounds 6] [--budget 300] [--locked-on-pass]
```

`scripts/run_phase.py` の `--json` / `--output-dir` 規約に倣い、`--json` フラグで NDJSON を stdout に流し、ログを stderr に向ける。

```
speca prompt-loop --phase 03 --rounds 3 --json
```

出力イベント例 (NDJSON):

```json
{"type":"round-started","phase":"03","round":1,"current_recall":0.47}
{"type":"critique-generated","round":1,"false_negatives":12,"prompt_length":3420}
{"type":"candidates-evaluated","round":1,"n_candidates":3,"best_recall":0.52}
{"type":"cross-client-check","round":1,"client_recall":{"geth":0.54,"nethermind":0.50}}
{"type":"round-completed","round":1,"recall":0.52,"cost_usd":44.10}
{"type":"prompt-locked","phase":"03","version":"v1","recall":0.61,"rounds_used":4}
```

### 5.2 ストリーミング進捗

`scripts/orchestrator/watchdog.py:LogWatcher` と同じ非同期テール方式でラウンド進捗を stdout に流す。`PromptOptimizer.run()` は各ラウンド終了時に `JsonEventEmitter` (既存: `scripts/orchestrator/json_events.py`) でイベントを発行する。

---

## 6. リスクと緩和策

### 6.1 Held-out スライスへの過学習

- **リスク:** 同一 100 レコードを 6 ラウンド評価し続けると、proposer が見逃しパターンを暗記する形でプロンプトを特化させる可能性がある。
- **緩和策 (判断呼び出し):** ラウンド 3 完了後に held-out スライスを再抽出するか否かは §8 の open question とする。再抽出する場合、ラウンド間でスコアが不連続になるため比較が困難になる。代替として Phase C 実行時に別の 100 レコードで事後確認を行う。

### 6.2 Cross-client 分布シフト

- **リスク:** EL クライアント (Geth, Reth 等) の過去修正データが CL クライアント (Lighthouse, Prysm 等) より多い場合、EL 特化プロンプトが生成される。
- **緩和策:** §3.3 の per-client recall チェックを全ラウンドで実施。Phase A 完成後、`source_platform` の分布を確認し held-out 抽出のストラトファイド条件に `source_platform` を含める。

### 6.3 コスト超過

- **リスク:** 1 ラウンドの eval + propose で $50 を超える場合、6 ラウンドで $300 上限に到達しない。
- **緩和策:** `CostTracker(max_budget_usd=50.0)` を各ラウンドに設定し `BudgetExceeded` で中断。超過した場合は候補数 (n_candidates) を 3 から 1 に削減して再試行する。コスト超過を繰り返すフェーズ (特に Phase 03: max_budget_usd=200.0) は eval のバッチサイズを削減する。

### 6.4 ベースライン benchmark への回帰

- **リスク:** held-out recall は向上しても、既存の rq1/rq2a/rq2b ベンチマークで性能が低下する。
- **緩和策:** locked 決定前に既存の CI テスト (`uv run python3 -m pytest tests/ -v --tb=short`) を通す。加えて、Phase A データのうち held-out 以外の slice (train split) で baseline との比較を行う。

### 6.5 プロンプト回帰 vs ベースライン

- **リスク:** ラウンドを重ねても recall が baseline を超えない場合、ロック基準を満たせない。
- **緩和策:** 最大 6 ラウンドで +10 pp に到達しない場合、最高スコアのプロンプトと改善量を記録してロックを保留し、§8 の open question として issue owner にエスカレーションする。

---

## 7. 実装計画 — 6 スライス (各々別 PR)

### Slice 1: Eval ハーネス skeleton

**対象ファイル:** `scripts/prompt_loop/eval_harness.py`, `tests/test_prompt_loop_harness.py`  
**内容:**
- `HeldOutSlice` (parquet から 100 レコード抽出、seed 固定)
- `EvalHarness.replay_phase()` — `introduced_in_commit` でリポジトリを checkout し、`ClaudeRunner` で replay
- `RecallScore` 算出ロジック
- モックフェッチャーでのユニットテスト

**Acceptance criteria:** `pytest tests/test_prompt_loop_harness.py` がパスする。モックデータで recall 計算が正確。

### Slice 2: Phase 04 の 1 フェーズ最適化 (最小ターゲット)

**対象ファイル:** `scripts/prompt_loop/optimizer.py`, `scripts/prompt_loop/generalization_check.py`  
**内容:**
- `PromptProposer` — Sonnet による critique + 改訂案生成
- `PromptSelector` — n=3 候補評価
- `PromptOptimizer.run()` を Phase 04 のみで動かすエンドツーエンドテスト
- cross-client チェック (Soft gate)
- コスト上限 $50/ラウンド の動作確認

**理由:** Phase 04 は `max_budget_usd=50.0` (デフォルト) かつ 1 バッチ 1 アイテムで最もコントローラブル。最初に動かして harness/optimizer の接続を確認する。  
**Acceptance criteria:** 1 ラウンドが $50 以内で完了し、recall スコアが記録される。

### Slice 3: Phase 01e / 02c / 03 への展開

**対象フィールド:** `PromptOptimizer` にフェーズ ID のパラメータ化を追加  
**内容:**
- Phase 03 (most expensive: max_budget_usd=200.0) の eval コスト測定
- Phase 01e / 02c の replay 接続 (01e は BUG_BOUNTY_SCOPE.json のモックが必要)
- per-phase recall ベースライン記録

**Acceptance criteria:** 各フェーズで 1 ラウンド eval が完走し、recall とコストが記録される。

### Slice 4: Phase 01a / 01b 対応

**内容:** Phase 01a/01b は skill-fork 形式のためプロンプトパスが `.claude/skills/` 以下にある。`PromptOptimizer` がこの違いを吸収する対応。  
**Acceptance criteria:** Phase 01b の eval ハーネスが `Phase01bOrchestrator._recover_partial_from_disk()` を正常に呼ぶ。

### Slice 5: Lock + Provenance

**対象ファイル:** `scripts/prompt_loop/provenance.py`, `prompts/eth-audit-2026/locked/` (Phase 03/04 の初期 locked プロンプト)  
**内容:**
- `ProvenanceManifest` Pydantic モデルと JSON 書き出し
- `prompts/eth-audit-2026/locked/<phase>/v1.md` の初期コミット
- `scripts/run_phase.py` への `--locked` フラグ追加

**Acceptance criteria:** `speca run --phase 03 --locked` が locked プロンプトを使って Phase 03 を実行する。

### Slice 6: `speca-cli` サーフェス

**対象ファイル:** `scripts/prompt_loop/cli.py`, `scripts/run_phase.py` (サブコマンド追加)  
**内容:**
- `speca prompt-loop --phase 03 --rounds 3` コマンド
- `--json` フラグによる NDJSON 出力
- ラウンドごとの recall + コスト表示
- `docs/SPECA_CLI_SPEC.md` へのコマンド追記

**Acceptance criteria:** `speca prompt-loop --phase 04 --rounds 1 --json` が NDJSON を stdout に流し stderr にログを出力する。

---

## 8. Slice 1 着手前に解決すべき Open Questions

以下の 5 点を issue #2 担当者 (grandchildrice) に確認する必要がある。回答が得られた後に §3 の設計を具体化する。

### Q1: Held-out スライスの固定 vs ラウンドごと再抽出

ラウンド全体で 100 レコードを固定すれば比較は容易だが、6 ラウンドのうちに proposer が false negative のパターンを暗記する形でプロンプトを特化させる過学習リスクがある。ラウンドごとに再抽出すればスコアが不連続になりラウンド間の改善量が測定できなくなる。現時点の推奨は「固定 held-out で最適化し、Phase C 実行前に別の 100 レコード (test split) で事後確認する」だが、この判断は issue owner に委ねる。

### Q2: Cross-client ゲートを Hard gate にするか Soft gate にするか

100 レコードを 11 クライアントで分割するとクライアントあたり平均 9 レコードとなり、1–2 レコードの差が recall に 10 pp 超の振れを生む。この精度でクライアント別の Hard gate (ラウンドブロック) を設けることは統計的に無意味な可能性が高い。現在の設計では Soft gate (警告のみ、`cross_client_check()` でログ出力) としているが、特定クライアントに対して厳格なゲートを設ける要件があれば変更する。

### Q3: `introduced_in_commit` のカバレッジ要件

`scripts/datasets/blame_walk.py` のコメント (L17-L19) では ISSUE# / CHANGELOG# ソース行は常に `""` となる (解決 TODO 状態)。Phase A 完了後に有効な `introduced_in_commit` を持つレコードが 100 件を確保できるかは現時点で不明。不足する場合、(a) held-out スライスを 50 件に縮小する、(b) ISSUE#/CHANGELOG# 行の resolving を Phase A の追加タスクとして前倒しする、(c) `GHSA-` / `PR#` / `RELEASE#` / `COMMIT#` ソース行のみに限定して 100 件を達成できるか確認する、という選択肢がある。

### Q4: eval replay 時のリポジトリ管理ポリシー

11 クライアント × 6 ラウンド × 複数フェーズの replay では、各クライアントリポジトリの bare clone とコミットチェックアウトのディスクコスト・時間コストが大きい。Phase B 実行環境 (ローカル vs CI) のディスク容量制限と、リポジトリのフルクローンが許容されるかのポリシーを明確にする必要がある。bare clone + `git worktree add --detach <commit>` 方式を推奨するが、CI 環境でのキャッシュ戦略 (actions/cache等) も検討が必要。

### Q5: TP トレーサビリティの許容精度

§3.1 で述べた「stride + cwe_top25 近似マッチング」による TP 判定の精度が受け入れられるか確認が必要。同一 stride/CWE ラベルを持つ別の脆弱性を誤って TP とカウントするリスクがある。より厳密なトレーサビリティ (例: held-out レコードの `source_url` と Phase 03 が参照したコードの commit SHA を突き合わせる) が必要か、あるいは近似マッチングで Phase B 評価として十分か。この判断により `EvalHarness.score()` の実装難易度が大きく変わる。

---

## References

1. Zhou et al., "Large Language Models Are Human-Level Prompt Engineers," arXiv:2211.01910 (2022). https://arxiv.org/abs/2211.01910
2. Yang et al., "Large Language Models as Optimizers," arXiv:2309.03409 (2023). https://arxiv.org/abs/2309.03409
3. Shinn et al., "Reflexion: Language Agents with Verbal Reinforcement Learning," NeurIPS 2023, arXiv:2303.11366. https://arxiv.org/abs/2303.11366
4. Madaan et al., "Self-Refine: Iterative Refinement with Self-Feedback," NeurIPS 2023, arXiv:2303.17651. https://arxiv.org/abs/2303.17651
5. Khattab et al., "DSPy: Compiling Declarative Language Model Calls into Self-Improving Pipelines," ICLR 2024, arXiv:2310.03714. https://arxiv.org/abs/2310.03714
6. Guo et al., "EvoPrompt: Connecting LLMs with Evolutionary Algorithms Yields Powerful Prompt Optimizers," ICLR 2024, arXiv:2309.08532. https://arxiv.org/abs/2309.08532
7. Fernando et al., "Promptbreeder: Self-Referential Self-Improvement Via Prompt Evolution," arXiv:2309.16797 (2023). https://arxiv.org/abs/2309.16797
8. Sheng et al., "LLMs in Software Security: A Survey of Vulnerability Detection Techniques and Insights," arXiv:2502.07049 (2025). https://arxiv.org/abs/2502.07049
9. Ma et al., "Combining Fine-Tuning and LLM-based Agents for Intuitive Smart Contract Auditing with Justifications," arXiv:2403.16073 (2024). https://arxiv.org/abs/2403.16073
10. Ramnath et al., "A Systematic Survey of Automatic Prompt Optimization Techniques," arXiv:2502.16923 (2025). https://arxiv.org/abs/2502.16923
