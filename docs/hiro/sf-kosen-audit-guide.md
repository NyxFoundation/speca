# sf-kosen org セキュリティ監査手順

## 前提

- 対象: プライベートリポジトリ群
- 脅威モデル: サービスの正規ユーザーが悪意を持つケースのみ想定
- ソースコード露出系の指摘は対象外

## 手順

### 1. ブランチを切る

対象組織名や担当者名でブランチを作成する。

```bash
cd security-agent
git checkout -b Fujisawa
```

### 2. outputs のゴミを確認・退避

前回の監査データが outputs/ に残っていると混ざるので、バックアップに退避する。

```bash
mkdir -p outputs_chainlink_backup
mv outputs/01a_* outputs/03_* outputs/04_* ... outputs_chainlink_backup/
```

### 3. org のスコープファイルを生成

`setup_org_audit.py` でリポジトリ一覧取得 + 各リポジトリのスコープファイルを自動生成。

```bash
uv run python3 scripts/setup_org_audit.py --org sf-kosen --output-base outputs_sf-kosen
```

生成されるファイル（リポジトリごと）:
- `TARGET_INFO.json` -- リポジトリ/ブランチ/コミット情報
- `BUG_BOUNTY_SCOPE.json` -- 監査スコープ定義
- `EXTRACTED_INPUTS.json` -- Phase 01a 用のキーワードとURL

空リポジトリ（例: API-Server）は除外される。

### 4. パイプラインで監査を実行

#### GitHub Actions 経由（推奨）

`.github/workflows/org-audit.yml` を手動トリガー。

- `org`: GitHub organization 名（例: `sf-kosen`）
- `repos`: 省略で全リポジトリ、指定でカンマ区切り
- matrix strategy でリポジトリごとに並列実行
- `SPECA_OUTPUT_DIR` でリポジトリごとに出力分離

#### ローカル実行

Windows 環境では SPECA パイプライン（`run_phase.py`）が `claude` CLI の subprocess 起動で問題が出る場合がある。その場合は Agent を並列で投入して直接コードを読ませて監査する。

```
Agent x 8 並列 → 各リポジトリを clone → 全ソース読込 → 脆弱性分析 → JSON レポート生成
```

レポートの保存先: `outputs_sf-kosen/{repo名}/security_audit_report.json`

### 5. 結果の評価

脅威モデルに照らして指摘をフィルタリングする。

除外する指摘:
- 「ハードコードされた秘密鍵が公開リポジトリに露出」→ プライベートリポなので無効
- ソースコード内の ID 露出 → 同上
- `.gitignore` のタイポでファイルがコミットされている → プライベートなので低リスク

残す指摘:
- ユーザー入力経由の攻撃（ReDoS, SSRF, インジェクション, 権限昇格）
- レート制限の欠如（ユーザーがスパム可能）
- 認可チェックの欠如（一般ユーザーが管理操作可能）

### 6. 修正 PR を出す

- fork → ブランチ作成 → 修正 → PR
- Co-Authored-By は付けない
- PR 本文は日本語
- レビューが返ってきたら対応してpush

### 7. サマリーの生成

全リポジトリの結果を集約:

```bash
python3 -c "
import json, glob
reports = []
for f in sorted(glob.glob('outputs_sf-kosen/*/security_audit_report.json')):
    with open(f, encoding='utf-8') as fh:
        r = json.load(fh)
        reports.append({'repo': r['repo'], 'summary': r['summary']})
print(json.dumps(reports, indent=2))
"
```

## 今回の監査結果（参考）

| Repository | Critical | High | Medium | Low | Info |
|---|---|---|---|---|---|
| mafuyu-AI | 3 | 6 | 6 | 3 | 4 |
| Nanase-Speaker-Bot | 2 | 4 | 5 | 3 | 3 |
| Nanase-Bot | 0 | 3 | 7 | 5 | 4 |
| discord-pow | 0 | 1 | 3 | 4 | 5 |
| brir-spatializer | 0 | 1 | 3 | 4 | 4 |
| homepage | 0 | 0 | 3 | 3 | 7 |
| keyshare | 0 | 0 | 4 | 4 | 5 |
| x-stream-server | 0 | 0 | 2 | 4 | 5 |

脅威モデル適用後の要対応:
- mafuyu-AI: 使われていないため対応不要
- Nanase-Speaker-Bot: ReDoS, SSRF, 権限チェック → PR #2
- Nanase-Bot: ticket認可, VC権限昇格, レート制限 → PR #40
