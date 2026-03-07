あなたは Codex クロスバリデーションのオーケストレーターです。
12 個の Codex CLI エージェントを並列起動して、Claude の発見を独立検証してください。

## セットアップ

cd /Users/hiro/Documents/security-agent

## ターゲット

TARGET="/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract"
OUTPUT_DIR="outputs/codex_results"

## 手順

1. outputs/codex_results/ ディレクトリを作成:
   mkdir -p outputs/codex_results

2. 以下の 12 コマンドを全て並列実行 (Bash ツールで & つき):

```bash
codex exec --skip-git-repo-check -s read-only -q \
  "あなたは Sui Move セキュリティ監査人。ターゲット: /Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/ 攻撃面: Flash Loan。borrow_flash_loan, repay_flash_loan, hot-potato パターン、手数料、再入を分析。各発見にタイトル、深刻度、ファイル名:行番号、コードスニペット、攻撃シナリオ、修正案を報告。" \
  > outputs/codex_results/01_flash_loan.md &

codex exec --skip-git-repo-check -s read-only -q \
  "あなたは Sui Move セキュリティ監査人。ターゲット: /Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/ 攻撃面: Oracle。oracle/user.move の get_price, get_spot_price, get_price_with_check, EMA vs Spot、deviation check、staleness を分析。各発見にタイトル、深刻度、ファイル名:行番号、コードスニペット、攻撃シナリオ、修正案を報告。" \
  > outputs/codex_results/02_oracle.md &

codex exec --skip-git-repo-check -s read-only -q \
  "あなたは Sui Move セキュリティ監査人。ターゲット: /Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/ 攻撃面: Liquidation。market.move の liquidation_inner, close_factor, seized amount, liquidation_revenue_factor, health check を分析。各発見にタイトル、深刻度、ファイル名:行番号、コードスニペット、攻撃シナリオ、修正案を報告。" \
  > outputs/codex_results/03_liquidation.md &

codex exec --skip-git-repo-check -s read-only -q \
  "あなたは Sui Move セキュリティ監査人。ターゲット: /Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/ 攻撃面: eMode。internal/emode.move の borrow cap tracking, collateral_factor, liquidation_factor, グループ間切替、admin 変更を分析。各発見にタイトル、深刻度、ファイル名:行番号、コードスニペット、攻撃シナリオ、修正案を報告。" \
  > outputs/codex_results/04_emode.md &

codex exec --skip-git-repo-check -s read-only -q \
  "あなたは Sui Move セキュリティ監査人。ターゲット: /Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/ 攻撃面: Interest Rate。market/reserve.move の accrue_interest, simple vs compound, borrow_index, cash_reserve 更新タイミングを分析。各発見にタイトル、深刻度、ファイル名:行番号、コードスニペット、攻撃シナリオ、修正案を報告。" \
  > outputs/codex_results/05_interest.md &

codex exec --skip-git-repo-check -s read-only -q \
  "あなたは Sui Move セキュリティ監査人。ターゲット: /Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/ 攻撃面: Access Control。internal/app.move の PackageCallerCap (key,store abilities), AdminCap, whitelist, permissions, ensure_has_permission を分析。各発見にタイトル、深刻度、ファイル名:行番号、コードスニペット、攻撃シナリオ、修正案を報告。" \
  > outputs/codex_results/06_access_control.md &

codex exec --skip-git-repo-check -s read-only -q \
  "あなたは Sui Move セキュリティ監査人。ターゲット: /Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/ 攻撃面: Rate Limiter。market/limiter.move の add_outflow, reduce_outflow, count_current_outflow, sliding window, segment 管理を分析。各発見にタイトル、深刻度、ファイル名:行番号、コードスニペット、攻撃シナリオ、修正案を報告。" \
  > outputs/codex_results/07_rate_limiter.md &

codex exec --skip-git-repo-check -s read-only -q \
  "あなたは Sui Move セキュリティ監査人。ターゲット: /Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/ 攻撃面: Deposit/Withdraw。market.move の handle_mint, handle_redeem, exchange rate, cToken supply, cash_plus_borrows_minus_reserves を分析。各発見にタイトル、深刻度、ファイル名:行番号、コードスニペット、攻撃シナリオ、修正案を報告。" \
  > outputs/codex_results/08_deposit_withdraw.md &

codex exec --skip-git-repo-check -s read-only -q \
  "あなたは Sui Move セキュリティ監査人。ターゲット: /Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/ 攻撃面: Referral。internal/referral.move の try_map_referral_code, generate_referral_code, deposit threshold, self-referral check を分析。各発見にタイトル、深刻度、ファイル名:行番号、コードスニペット、攻撃シナリオ、修正案を報告。" \
  > outputs/codex_results/09_referral.md &

codex exec --skip-git-repo-check -s read-only -q \
  "あなたは Sui Move セキュリティ監査人。ターゲット: /Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/ 攻撃面: Auto-Deleverage (ADL)。market/adl.move の enable_collateral_deleverage, enable_debt_deleverage, try_stop, activation vs stop scope を分析。各発見にタイトル、深刻度、ファイル名:行番号、コードスニペット、攻撃シナリオ、修正案を報告。" \
  > outputs/codex_results/10_adl.md &

codex exec --skip-git-repo-check -s read-only -q \
  "あなたは Sui Move セキュリティ監査人。ターゲット: /Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/ 攻撃面: Math/Precision。contracts/math/sources/float.move の int_mul (floor truncation), mul, div, ceil, 丸め方向、overflow を分析。各発見にタイトル、深刻度、ファイル名:行番号、コードスニペット、攻撃シナリオ、修正案を報告。" \
  > outputs/codex_results/11_math_precision.md &

codex exec --skip-git-repo-check -s read-only -q \
  "あなたは Sui Move セキュリティ監査人。ターゲット: /Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/ 攻撃面: Reserve/Revenue。market/reserve.move の take_revenue, cash_reserve, repay_amount, flash loan fee routing, protocol fee を分析。各発見にタイトル、深刻度、ファイル名:行番号、コードスニペット、攻撃シナリオ、修正案を報告。" \
  > outputs/codex_results/12_reserve_revenue.md &

wait
```

3. 全 12 ファイルの結果を読み込む

4. 既存の Claude レポート (outputs/reports/ の 001-027) と比較:
   - 両方が確認 → 信頼度 HIGH、既にレポート済みなのでスキップ
   - Codex のみ新規発見 → ソースコードで検証し、有効ならレポート作成

5. 新規発見があればレポート作成 → コミット → PR → 即マージ
