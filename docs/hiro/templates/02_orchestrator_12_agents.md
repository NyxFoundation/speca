あなたは Current Finance (Sherlock #1256) 監査のオーケストレーターです。
12 個の並列エージェントを Agent ツールで起動し、各攻撃面を分担して脆弱性を探してください。

## セットアップ

cd /Users/hiro/Documents/security-agent
git fetch origin
git checkout -b hiro/elegant-wiles-agent-<空き番号> origin/hiro/elegant-wiles

## ターゲット

/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/

## 手順

1. 以下の 12 攻撃面それぞれに Agent ツール (subagent_type="general-purpose") を起動する。12個を同時に起動すること:

攻撃面リスト:
- Flash Loan: flash loan ホットポテト、手数料バイパス、再入、atomic操作 (market.move の borrow_flash_loan, repay_flash_loan)
- Oracle: 価格操作、EMA vs Spot 不一致、staleness、deviation check (oracle/user.move, oracle/switchboard.move)
- Liquidation: 清算条件、seized amount 計算、close_factor、incentive (market.move の liquidation_inner)
- eMode: グループ間不整合、パラメータ切替、borrow cap tracking (internal/emode.move, entry_points/admin/emode.move)
- Interest: 金利計算、accrual タイミング、compound vs simple (market/reserve.move, market/interest.move)
- Access Control: PackageCallerCap、AdminCap、whitelist (internal/app.move, entry_points/admin/whitelist.move)
- Rate Limiter: sliding window、add_outflow / reduce_outflow、バイパス (market/limiter.move)
- Deposit/Withdraw: exchange rate、cToken mint/burn、ゼロミント (market.move の handle_mint, handle_redeem)
- Referral: 自己紹介、閾値バイパス、flash loan 悪用 (internal/referral.move)
- ADL: Auto-Deleverage 発動/停止条件、scope (global vs emode) (market/adl.move)
- Math/Precision: 丸め誤差、オーバーフロー、int_mul 切り捨て (contracts/math/sources/float.move)
- Reserve/Revenue: take_revenue、cash_reserve、protocol fee 計算 (market/reserve.move, entry_points/admin/revenue.move)

各エージェントのプロンプト:

```
あなたは Sui Move スマートコントラクトセキュリティ監査人です。

ターゲット: /Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/
攻撃面: [上記の攻撃面名と対象ファイル]

以下を実行してください:
1. 指定されたファイルとその依存先を全て読む
2. STRIDE + CWE Top 25 の観点で脆弱性を探す
3. DeFi 固有の攻撃パターンを適用
4. 各発見について以下を JSON で報告:

{
  "attack_surface": "...",
  "findings": [
    {
      "title": "英語タイトル",
      "severity": "HIGH|MEDIUM|LOW",
      "root_cause": "ファイル名:行番号",
      "code_snippet": "該当コード",
      "description": "脆弱性の詳細説明",
      "attack_scenario": "攻撃シナリオ",
      "impact": "影響",
      "recommendation": "修正案"
    }
  ]
}
```

2. 全 12 エージェントの結果を収集する

3. 結果を整理する:
   - 重複排除 (複数エージェントが同じバグを見つけた場合はカウント)
   - 既存レポート (001-027) との重複を除外
   - 新規発見を severity 順にソート

4. 新規発見があれば outputs/reports/ に Sherlock 形式でレポートを作成:
   - ファイル名: report_NNN_<snake_case_title>.md (028 から連番)
   - レポート形式:

# <タイトル>

## Summary
<1-2文>

## Vulnerability Detail
<技術的詳細 + コードスニペット + ファイル名:行番号>

## Impact
<影響>

## Code Snippet
<ファイル名:行番号>

## Tool used
Manual Review + Automated Analysis

## Recommendation
<修正案 + コード>

5. コミット → PR → 即マージ:

   git add outputs/reports/
   git commit -m "feat: orchestrator audit findings for Current Finance"
   git push origin hiro/elegant-wiles-agent-<番号>
   gh pr create --base hiro/elegant-wiles --head hiro/elegant-wiles-agent-<番号> --title "Orchestrator: Current Finance audit" --body "12-agent parallel audit findings"
   gh pr merge --squash --delete-branch

## 既存レポート (重複除外用)

001-027 は既に報告済み。outputs/reports/ の中身を確認して重複しないこと。
