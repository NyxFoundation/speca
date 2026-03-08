あなたは Current Finance / Pebble (Sherlock #1256) の SPECA パイプライン実行エージェントです。
定義済みスキーマに基づく体系的なセキュリティ監査を実行してください。

## 作業環境セットアップ

1. SPECA リポジトリに移動:
   cd /Users/hiro/Documents/security-agent

2. ブランチ作成:
   git fetch origin
   git checkout -b hiro/elegant-wiles-speca-inst-<INSTANCE_NUMBER> origin/hiro/elegant-wiles
   (INSTANCE_NUMBER は空き番号を git branch -r で確認して決定。01, 02, 03... の中で使われていないもの)

## Step 1: 共有フェーズの確認と実行

outputs/ に共有フェーズの出力があるか確認:

```bash
ls outputs/01a_STATE.json outputs/BUG_BOUNTY_SCOPE.json outputs/TARGET_INFO.json 2>/dev/null
```

01a_STATE.json は既に作成済み。

01b (サブグラフ抽出) と 01e (プロパティ生成) がまだの場合:
- 01b_PARTIAL_*.json が存在するか確認
- 01e_PARTIAL_*.json が存在するか確認
- 存在しなければ以下を実行 (1回だけ。他のインスタンスが既に走らせていたらスキップ):

```bash
uv run python3 scripts/run_phase.py --phase 01b 01e --workers 4
```

注意: 01b/01e は共有データなので、複数インスタンスが同時に走らせると重複する。
ファイルが存在するなら実行しないこと。ロックファイルで排他制御:

```bash
if [ ! -f outputs/.01b_running ] && [ ! -f outputs/01b_PARTIAL_*.json 2>/dev/null ]; then
  touch outputs/.01b_running
  uv run python3 scripts/run_phase.py --phase 01b 01e --workers 4
  rm -f outputs/.01b_running
fi
```

## Step 2: インスタンスディレクトリ準備

自身のインスタンスディレクトリを作成し、共有データをリンク:

```bash
INST_DIR="outputs/inst_<INSTANCE_NUMBER>"
mkdir -p "$INST_DIR"

# 共有フェーズ出力をシンボリックリンク
ln -sf ../01a_STATE.json "$INST_DIR/"
for f in ../01b_PARTIAL_*.json; do ln -sf "$f" "$INST_DIR/" 2>/dev/null; done
for f in ../01e_PARTIAL_*.json; do ln -sf "$f" "$INST_DIR/" 2>/dev/null; done
ln -sf ../graphs "$INST_DIR/" 2>/dev/null
ln -sf ../BUG_BOUNTY_SCOPE.json "$INST_DIR/"
ln -sf ../01b_SUBGRAPH_INDEX.json "$INST_DIR/" 2>/dev/null

# TARGET_INFO.json をコピー
cp outputs/TARGET_INFO.json "$INST_DIR/"
```

## Step 3: SPECA パイプライン実行 (02c→03→04)

```bash
SPECA_OUTPUT_DIR="$INST_DIR" uv run python3 scripts/run_phase.py --phase 02c 03 04 --workers 2
```

## Step 4: 結果確認

実行完了後、結果を確認:

```bash
# Phase 04 の出力 (レビュー済み結果)
ls "$INST_DIR"/04_PARTIAL_*.json

# CONFIRMED 発見の一覧
python3 -c "
import json, glob
for f in sorted(glob.glob('$INST_DIR/04_PARTIAL_*.json')):
    data = json.load(open(f))
    items = data if isinstance(data, list) else data.get('reviewed_items', data.get('items', []))
    for item in items:
        verdict = item.get('review_verdict', item.get('verdict', 'UNKNOWN'))
        if verdict in ('CONFIRMED_VULNERABILITY', 'CONFIRMED_POTENTIAL'):
            print(f'{verdict}: {item.get(\"property_id\", \"?\")} - {item.get(\"title\", item.get(\"property_statement\", \"?\")[:80]}')
"
```

## Step 5: 結果をコミット + PR

```bash
git add "$INST_DIR"/
git commit -m "feat: SPECA instance <INSTANCE_NUMBER> audit results for Current Finance"
git push origin hiro/elegant-wiles-speca-inst-<INSTANCE_NUMBER>

gh pr create \
  --base hiro/elegant-wiles \
  --head hiro/elegant-wiles-speca-inst-<INSTANCE_NUMBER> \
  --title "SPECA Instance <INSTANCE_NUMBER>: Current Finance audit results" \
  --body "SPECA pipeline (02c→03→04) results from instance <INSTANCE_NUMBER>" \
  --repo NyxFoundation/security-agent

gh pr merge --squash --delete-branch --repo NyxFoundation/security-agent
```

## ターゲット情報

- プロトコル: Current Finance (Pebble)
- チェーン: Sui
- 言語: Sui Move
- コンテスト: Sherlock #1256
- ターゲットコード: /Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources
- Oracle: /Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/x_oracle/sources

## 主要な監査ポイント

- Flash Loan: hot-potato パターン、手数料、reentrancy (1 PTB 内で deposit/borrow)
- Exchange rate / cToken / borrow index の整合性
- eMode: obligation 作成後の切り替え不可の不変量
- Liquidation: bad debt シナリオ、close factor
- Oracle: 価格操作、staleness
- Rate Limiter: sliding window バイパス
- 数学精度: floor truncation, overflow, WAD conversion

## 重要な注意

- SPECA パイプラインの各フェーズは Pydantic スキーマで出力を検証する
- Phase 03 は proof-based: プロパティの成立を証明し、ギャップが発見となる
- Phase 04 は 3-gate FP フィルタ: Dead Code → Trust Boundary → Scope Check
- 失敗したら CircuitBreaker のログを確認: outputs/logs/ 配下
- --force フラグで再実行可能
