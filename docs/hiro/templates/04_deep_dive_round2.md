あなたは Current Finance (Sherlock #1256) 監査の深堀りラウンド 2 を担当します。
ラウンド 1 で見つかった脆弱性を踏まえ、まだ発見されていない問題を徹底的に探してください。

## セットアップ

cd /Users/hiro/Documents/security-agent
git fetch origin
git checkout -b hiro/elegant-wiles-agent-<空き番号> origin/hiro/elegant-wiles

## ターゲット

/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/

## 手順

1. まず outputs/reports/ の既存レポート全てを読んで、発見済みの脆弱性を把握する

2. 以下の 12 深堀りテーマで Agent ツール (subagent_type="general-purpose") を 12 個同時起動する:

各エージェントに渡すプロンプトのテンプレート:

```
あなたは Sui Move セキュリティ監査人です。深堀りラウンド 2 を行います。

ターゲット: /Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/

[テーマ名]: [具体的な深堀り指示]

ラウンド 1 で既に以下が見つかっています。これらとは異なる新しい脆弱性のみを報告してください:
[既存レポートの一覧を貼り付け]

各発見について JSON で報告:
{
  "title": "...",
  "severity": "HIGH|MEDIUM|LOW",
  "root_cause": "ファイル名:行番号",
  "code_snippet": "...",
  "description": "...",
  "impact": "...",
  "recommendation": "..."
}
```

12 テーマ:
- Withdraw/Redeem: handle_redeem のフロー全体、health check 後の状態変更、exchange rate 操作
- Rate Limiter 深堀り: reduce_outflow のクロスセグメント問題、admin 更新によるリセット、清算バイパスの他の経路
- Oracle 深堀り: Switchboard アダプター、Pyth アダプター、価格キャッシュの TTL、フォールバックロジック
- Interest Accrual 深堀り: borrow_index 更新順序、reserve_factor の端数処理、同一ブロック内の複数操作
- Obligation Health: health check のタイミング、refresh_obligation の呼び出し順序、eMode 切替時の health
- Flash Loan Combo: flash loan + 他操作の組合せ攻撃、atomic な状態変更チェーン
- Deposit/cToken: exchange rate 初期化、first depositor 攻撃、大量 mint/burn
- Repay/Debt: 部分返済の端数、debt clearing 条件、overpayment 処理
- eMode Switching: eMode 変更時の既存 obligation への影響、migration パス
- Revenue/Reserve: take_revenue 前後の状態、cash_reserve の不整合、fee 計算
- Liquidation Incentive: liquidation_incentive の計算、over-liquidation、MEV
- Value Precision: Decimal 演算の精度損失、WAD 変換、large number handling

3. 全エージェント結果を収集、重複除外、既存レポートとの照合

4. 新規発見を outputs/reports/ にレポート化 (028 から連番)

5. コミット → PR → 即マージ:
   git add outputs/reports/
   git commit -m "feat: deep-dive round 2 findings for Current Finance"
   git push origin hiro/elegant-wiles-agent-<番号>
   gh pr create --base hiro/elegant-wiles --head hiro/elegant-wiles-agent-<番号> --title "Deep-dive R2: Current Finance" --body "Round 2 deep-dive findings"
   gh pr merge --squash --delete-branch
