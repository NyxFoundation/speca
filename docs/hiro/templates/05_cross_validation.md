あなたは Current Finance (Sherlock #1256) 監査のクロスバリデーション担当です。
Claude エージェントの発見と Codex エージェントの発見を比較し、新規発見をレポート化してください。

## セットアップ

cd /Users/hiro/Documents/security-agent
git fetch origin
git checkout -b hiro/elegant-wiles-agent-<空き番号> origin/hiro/elegant-wiles

## ターゲット

/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/

## 手順

1. outputs/reports/ の全レポートを読む (既存の Claude 発見)

2. outputs/codex_results/ の全ファイルを読む (Codex 発見)

3. 比較マトリクスを作成:

| 発見 | Claude | Codex | 状態 |
|------|--------|-------|------|
| ... | report_NNN で報告済 | 確認 | 既報告 |
| ... | 未発見 | 発見 | 要検証 |
| ... | 発見 | 未確認 | 既報告 |

4. Codex のみが発見した項目について:
   - ターゲットコードの該当箇所を実際に読む
   - 脆弱性が本物かどうかソースコードで検証する
   - 本物であればレポートを作成

5. 全体の発見について、以下を outputs/reports/ に書き出す:
   - 新規発見のレポート (Sherlock 形式)
   - ファイル名: report_NNN_<snake_case_title>.md

6. コミット → PR → 即マージ:
   git add outputs/reports/
   git commit -m "feat: cross-validation findings for Current Finance"
   git push origin hiro/elegant-wiles-agent-<番号>
   gh pr create --base hiro/elegant-wiles --head hiro/elegant-wiles-agent-<番号> --title "Cross-validation: Current Finance" --body "Cross-validation of Claude + Codex findings"
   gh pr merge --squash --delete-branch
