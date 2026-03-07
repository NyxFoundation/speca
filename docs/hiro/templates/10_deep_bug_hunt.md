あなたは Current Finance (Sherlock #1256) の Sui Move DeFi レンディングプロトコルのセキュリティ監査人です。
下調べ・環境構築は完了済み。コードを読んでバグを探し、レポートを書き、PRを送ることだけに集中してください。

## セットアップ (最小限)

```bash
cd /Users/hiro/Documents/security-agent
git fetch origin
git checkout -b hiro/elegant-wiles-agent-<N> origin/hiro/elegant-wiles
```
<N> は `git branch -r | grep elegant-wiles-agent` で未使用の最若番号。

## ターゲットコード

パス: `/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract`

### コアモジュール (最重要 — ここにバグがある)
| ファイル | 行数 | 内容 |
|---------|------|------|
| `contracts/protocol/sources/internal/market/market.move` | ~1300 | 全操作の中核: deposit/withdraw/borrow/repay/liquidation/ADL/flash_loan |
| `contracts/protocol/sources/internal/market/reserve.move` | ~330 | 準備金、exchange_rate、cToken mint/burn、cash/debt 管理 |
| `contracts/protocol/sources/internal/market/obligation.move` | ~300 | ユーザー債務状態、ctoken deposit/withdraw、safety check |
| `contracts/protocol/sources/internal/market/emode.move` | ~400 | eMode グループ、資産設定、borrow/deposit limiter |
| `contracts/protocol/sources/internal/market/adl.move` | ~210 | Auto-Deleverage、時間減衰 LTV、incentive |
| `contracts/protocol/sources/internal/market/limiter.move` | ~170 | Sliding window rate limiter |
| `contracts/protocol/sources/internal/market/interest.move` | ~50 | Kink モデル金利計算 |
| `contracts/protocol/sources/internal/market/debt.move` | ~60 | 個別債務、borrow index ベース計算 |
| `contracts/math/sources/float.move` | ~130 | WAD (10^18) 固定小数点演算 |

### エントリポイント (攻撃面)
| ファイル | 外部公開関数 |
|---------|------------|
| `entry_points/lending/deposit.move` | deposit |
| `entry_points/lending/withdraw.move` | withdraw |
| `entry_points/lending/borrow.move` | borrow |
| `entry_points/lending/repay.move` | repay |
| `entry_points/lending/flash_loan.move` | borrow_flash_loan, repay_flash_loan |
| `entry_points/lending/liquidate.move` | liquidate, debt_auto_deleverage, collateral_auto_deleverage |
| `entry_points/lending/enter_market.move` | create_obligation |
| `entry_points/lending/liquidity_mining.move` | claim_rewards |
| `entry_points/referral.move` | create_referral, update_referral |
| `entry_points/admin/*.move` | 各種admin操作 |

### Oracle
| ファイル | 内容 |
|---------|------|
| `contracts/x_oracle/sources/internal/x_oracle.move` | 価格取得ロジック |
| `contracts/x_oracle/sources/internal/pyth_adaptor.move` | Pyth 連携、EMA/Spot |
| `contracts/x_oracle/sources/internal/price_feed.move` | 価格正規化 |

## プロトコル設計の要点

- **Sui Move**: Programmable Transaction Block (PTB) 内で複数操作を原子的に実行可能
- **cToken モデル**: deposit → cToken mint (exchange_rate = (cash + debt - reserves) / supply)
- **eMode**: 資産はグループに属し、グループ内でのみ担保/借入可能
- **Flash Loan**: hot-potato パターン (borrow → 任意操作 → repay を同一 PTB 内で強制)
- **Liquidation**: close_factor 制限あり、bad debt 近傍 (101%) で bypass
- **ADL**: 時間減衰 LTV で段階的に閾値を下げ強制清算
- **Rate Limiter**: sliding window 方式で急激な出金を制限
- **Interest**: simple interest (複利ではない)、borrow index 方式
- **WAD 演算**: u256 内部、floor truncation が基本

## 既存レポート一覧 (50件 — 絶対に重複しないこと)

### ADL 関連
001: ADL borrow が担保を差し押さえる (HIGH)
004: ADL borrow グローバル debt チェック不足 (HIGH)
030: ADL floor/ceil 不整合 — trigger/stop 境界で振動
035: ADL LTV が時間経過でゼロまで低下
038: ADL cancel_collateral のタイムスタンプ単位不一致 (ms vs s)
038: ADL ゼロ担保 obligation で除算エラー abort
039: ADL が liquidation_paused を無視 (×2 重複レポート)

### 清算関連
002: 静的 close_factor による過剰清算 (HIGH)
003: 清算時 Spot vs EMA 価格不一致 (HIGH)
008: 清算がレートリミッターを回避
011: 清算手数料バイパス (チャンキング)
029: 清算が debt 側の pause 未チェック
031: サーキットブレーカーが清算をブロック
036: 清算が min_borrow_amount チェックなし → dust debt 生成
042: 清算後の health check なし → 戦略的 debt 選択

### Flash Loan 関連
006: Flash loan referral バイパス
010: Flash loan deposit リミッター操作
018: Cross-eMode flash loan fee 回避
036: Flash loan 中 cash フィールド未更新 (stale state)

### eMode 関連
005: eMode borrow tracking desync
015: eMode admin timelock なし
040: Admin eMode 資産削除で obligation 凍結
040: サーキットブレーカーが repay をブロック

### Oracle 関連
009: Oracle deviation 非対称
022: Oracle staleness 悪用可能
026: Pyth adapter 起動時 underflow
035: Pyth normalize_decimals 精度切り捨て

### 金利/Reserve 関連
012: 同一秒ゼロ金利借入
014: take_revenue 金利未反映
017: 利用率 1.0 超過可能
024: 単利 (複利ではない)
027: Repay 丸め過剰請求
032: deposit_limit 二重減算
037: handle_borrow 担保側金利 stale
041: deposit_limit_breached u64 underflow で全 deposit ブロック
043: Reserve vs obligation の phantom debt 乖離

### Limiter 関連
016: リミッターが token 量ベース (USD 非対応)
021: Cross-segment limiter の reduce_outflow 不具合
025: Admin eMode 更新で limiter リセット

### 報酬 関連
033: Liquidity mining ゼロシェア期間の報酬消失
034: Borrow reward share staleness
037: Reward dust が永久ロック

### アクセス制御
007: burn_whitelist に AdminCap チェックなし
013: PackageCallerCap が transferable (key+store)

### その他
019: Sybil 自己紹介
020: ゼロミント deposit griefing
023: Borrow off-by-one
028: Dust obligation が清算不能
028: 無制限 token decimals で protocol abort

## 探索すべき未開拓領域

以下は既存レポートでカバーが薄い領域。優先的に調査せよ:

1. **PTB 内の cross-function composability**
   - deposit → borrow → withdraw を同一 PTB で実行した場合の状態整合性
   - flash_loan 内で obligation 操作 (deposit/borrow) を行った場合の副作用
   - 複数 obligation に跨る操作の ordering 依存性

2. **Value 計算の精度**
   - `value.move` の coin_value 関数の丸め方向
   - collaterals_usd / debts_usd 計算でのリスク集約精度
   - 異なる decimals の asset 間での USD 変換誤差

3. **Admin 操作のエッジケース**
   - asset 設定変更 (LTV, liquidation_factor 等) の即時反映 vs 遅延反映
   - market 設定変更中の inflight 操作との競合
   - whitelist 追加/削除のレースコンディション

4. **Obligation ライフサイクル**
   - create_obligation 後、最初の deposit 前の状態
   - 全 collateral withdraw 後、debt だけ残る状態
   - 複数 eMode グループ資産の相互作用

5. **Revenue / 手数料の抜け漏れ**
   - take_revenue のタイミング依存
   - flash loan fee が reserve に正しく反映されるか
   - liquidation revenue_factor のエッジケース

6. **Generic Store / Wit Table**
   - 型安全性の境界
   - 動的フィールドの一貫性

## 作業手順

1. ターゲットコードを読む (上記モジュール表の順序で)
2. 脆弱性を発見したら `outputs/reports/` に Sherlock 形式で報告
3. ファイル名: `report_NNN_<snake_case_title>.md` (NNN は 044 から連番)
4. HIGH/MEDIUM 優先。推測ではなく、コードを読んで確認した脆弱性のみ

### レポート形式

```markdown
# <タイトル (英語)>

## Summary
<1-2文の要約>

## Vulnerability Detail
<技術的詳細、コードスニペット付き。根本原因のファイル名:行番号を明記>

## Impact
<影響の説明>

## Code Snippet
<ファイル名:行番号のリスト>

## Tool used
Manual Review + Automated Analysis

## Recommendation
<修正案、コードスニペット付き>
```

## 完了後

```bash
git add outputs/reports/
git commit -m "feat: agent-<N> audit findings for Current Finance"
git push origin hiro/elegant-wiles-agent-<N>

gh pr create \
  --base hiro/elegant-wiles \
  --head hiro/elegant-wiles-agent-<N> \
  --title "Agent <N>: Current Finance audit findings" \
  --body "Automated audit findings from agent session <N>" \
  --repo NyxFoundation/security-agent

gh pr merge --squash --delete-branch --repo NyxFoundation/security-agent
```

## 重要

- 既存 50 レポートと重複するものは書かない
- コードスニペットは必ずファイル名と行番号を含める
- 推測ではなく、実際のコードを読んで確認した脆弱性のみ報告
- レポートは `outputs/reports/` に配置
