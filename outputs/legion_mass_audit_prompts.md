# Legion Protocol — 20並列Claude手動監査プロンプト

> 使い方: 各プロンプトを別々のClaude Codeセッションにコピペして実行
> 作業ディレクトリ: `C:/Users/shieru_k/Documents/security-agent`
> ターゲット: `target_workspace/legion-protocol-contracts/src/`
> 類似コンテストCSV: `outputs/legion_similar_issues.csv` (5,354件)

---

## Session 01: Sealed Bid Auction — Commit/Reveal Scheme

```
あなたはSolidity監査人です。Legion ProtocolのSealed Bid Auction実装を監査してください。

ターゲット: C:/Users/shieru_k/Documents/security-agent/target_workspace/legion-protocol-contracts/src/sales/LegionSealedBidAuctionSale.sol

重点チェック:
- commit/reveal schemeの実装に不備がないか
- bid commit後のreveal期間中のfront-running可能性
- 未revealのbidの扱い（ロック資金の返還ロジック）
- bid金額の検証（min/max bid）
- 同額bidの優先順位ロジック
- reveal期間後の清算ロジック

参考パターンCSV: C:/Users/shieru_k/Documents/security-agent/outputs/legion_similar_issues.csv
上記CSVから severity=High AND (title OR description に sealed, bid, auction, reveal, commit を含む) 行を抽出し、パターンを照合せよ。

発見事項はJSON形式で outputs/manual_audit_01_sealed_bid.json に保存。
```

## Session 02: Merkle Proof — Eligibility Bypass

```
あなたはSolidity監査人です。Legion ProtocolのMerkle Proof検証を監査してください。

ターゲットファイル:
- C:/Users/shieru_k/Documents/security-agent/target_workspace/legion-protocol-contracts/src/sales/LegionAbstractSale.sol
- 同ディレクトリの全Sale実装

重点チェック:
- Merkle proofの検証ロジック（leaf構築、ダブルハッシュ対策）
- 同一proofの複数回使用（replay）
- leaf構築時のabi.encodePackedのcollision（異なる入力で同じleaf生成）
- claimTokenAllocation, withdrawExcessInvestedCapital でのproof検証
- proofなしで呼べる関数の特定

参考: outputs/legion_similar_issues.csv から merkle, proof, allowlist, whitelist を含む行を抽出して照合。

発見事項は outputs/manual_audit_02_merkle.json に保存。
```

## Session 03: Vesting Contract Deployment

```
あなたはSolidity監査人です。Legion Protocolのvesting系コントラクトを監査してください。

ターゲット:
- C:/Users/shieru_k/Documents/security-agent/target_workspace/legion-protocol-contracts/src/vesting/
- claimTokenAllocation内の_createVesting呼び出し

重点チェック:
- vestingコントラクトの初期化（パラメータ検証）
- vesting scheduleの計算精度（cliff, duration, rate）
- release()のタイミング操作
- vestingアドレスの二重デプロイ
- vestingコントラクトへのトークン送信とrelease可能量の整合性
- TGEレートとvesting分のトークン配分計算（丸め誤差）

発見事項は outputs/manual_audit_03_vesting.json に保存。
```

## Session 04: Factory + EIP-1167 Proxy Initialization

```
あなたはSolidity監査人です。Legion ProtocolのFactory契約とEIP-1167 Minimal Proxy実装を監査してください。

ターゲット:
- C:/Users/shieru_k/Documents/security-agent/target_workspace/legion-protocol-contracts/src/factories/

重点チェック:
- Minimal Proxyのinitialize()が二重呼び出し可能か
- initialize前にproxy関数を呼べるか
- factory経由でない直接デプロイの可能性
- implementation contractのselfdestruct/destroy可能性
- cloneのdeterministic addressと衝突
- initialize()でのパラメータ検証漏れ

参考: outputs/legion_similar_issues.csv から proxy, clone, initializ, factory を含む行を照合。

発見事項は outputs/manual_audit_04_factory.json に保存。
```

## Session 05: Fee Calculation & Token Distribution

```
あなたはSolidity監査人です。Legion ProtocolのFee計算とトークン分配ロジックを監査してください。

ターゲット:
- LegionAbstractSale.sol の supplyTokens(), claimTokenAllocation()
- src/distribution/ 以下

重点チェック:
- legionFee, referrerFee の計算精度（除算の丸め方向）
- fee計算とトークン残高の整合性（最後のclaimで残高不足にならないか）
- TOKEN_ALLOCATION_RATE_DENOMINATOR の使い方
- amountToDistributeOnClaim + amountToBeVested = amount が常に成立するか
- supplyTokens時のamount検証 vs 実際のclaim可能量
- fee receiverが0アドレスの場合

発見事項は outputs/manual_audit_05_fees.json に保存。
```

## Session 06: Refund Logic Edge Cases

```
あなたはSolidity監査人です。Legion Protocolの返金ロジックを監査してください。

ターゲット:
- LegionAbstractSale.sol の refund(), emergencyWithdraw()
- LegionPreLiquidApprovedSale.sol の refund系
- LegionCapitalRaise.sol の refund系

重点チェック:
- refund後にclaimTokenAllocationを呼べないか（_verifyHasNotRefunded）
- 二重refund防止
- refund期間の境界条件（ちょうどrefundPeriod終了時）
- emergencyWithdraw vs refund の状態遷移の整合性
- refund時のトークン返還量計算
- cancel後のrefundパス

発見事項は outputs/manual_audit_06_refund.json に保存。
```

## Session 07: Position Manager — SBT Transfer Edge Cases

```
あなたはSolidity監査人です。Legion ProtocolのPosition Manager (SBT)を深堀り監査してください。

ターゲット:
- src/position/LegionPositionManager.sol
- _burnOrTransferInvestorPosition の全実装

重点チェック:
- transferInvestorPosition vs transferInvestorPositionWithAuthorization の権限差
- ポジションmerge時の投資額計算（overflow可能性）
- burn後のポジションIDの再利用可能性
- _getInvestorPositionId が 0 を返すケース
- ポジションが存在しないIDでの関数呼び出し
- SBT (ERC5192) のlocked状態とtransferの整合性

発見事項は outputs/manual_audit_07_position.json に保存。
```

## Session 08: Access Control Coverage Analysis

```
あなたはSolidity監査人です。Legion Protocol全体のアクセス制御を網羅的に監査してください。

ターゲット: src/ 以下全ファイル

重点チェック:
- onlyLegion, onlyProject, onlyOwner の定義と適用箇所を全列挙
- external/public関数でmodifierが欠落している関数の特定
- whenNotPaused が必要なのに付いていない関数
- whenSaleNotCanceled が必要なのに付いていない関数
- modifier の順序による副作用（gas消費の観点ではなくセキュリティ）
- LegionBouncer のロール管理

全external/public関数のmodifier一覧表をCSV形式で outputs/manual_audit_08_access_control.csv に保存。
```

## Session 09: Reentrancy Analysis

```
あなたはSolidity監査人です。Legion Protocol全体のリエントランシー脆弱性を監査してください。

ターゲット: src/ 以下全ファイル

重点チェック:
- external call (safeTransfer, safeTransferFrom, call) の後にstate変更がないか
- ERC777/hookableトークンを bidToken/askToken に設定した場合の影響
- claimTokenAllocation → _createVesting → safeTransfer のフロー
- refund() → safeTransfer のフロー
- cross-function reentrancy（別の関数を再入呼び出し）
- read-only reentrancy（view関数が古いstateを返す）

CEI (Checks-Effects-Interactions) パターン違反を全列挙。
発見事項は outputs/manual_audit_09_reentrancy.json に保存。
```

## Session 10: Capital Raise Lifecycle

```
あなたはSolidity監査人です。Legion ProtocolのCapital Raise実装を監査してください。

ターゲット: src/raise/LegionCapitalRaise.sol

重点チェック:
- invest → publishResults → supplyTokens → claimTokenAllocation のライフサイクル全体
- cachedTokenAllocationRate の更新タイミングとrace condition
- capital raise固有のmodifier（whenRaiseEnded等）の整合性
- LegionAbstractSaleと共通の脆弱性パターンがCapitalRaiseにも存在するか
- CapitalRaise固有のロジック（AbstractSaleにないもの）の脆弱性

発見事項は outputs/manual_audit_10_capital_raise.json に保存。
```

## Session 11: PreLiquid Approved Sale — SAFT Flow

```
あなたはSolidity監査人です。Legion ProtocolのPreLiquid Approved Sale (SAFT)を監査してください。

ターゲット: src/sales/LegionPreLiquidApprovedSale.sol (1078行)

重点チェック:
- investWithSignature のsignature検証フロー
- s_usedSignatures の管理（invest署名 vs transfer署名の保護範囲の差）
- SAFT固有のclaimTokenAllocation（vestingSignature + claimSignature）
- convertPosition のロジック（Pre-TGE → Post-TGE変換）
- whenSaleResultsNotPublished vs whenSaleResultsArePublished の境界
- 二重invest防止ロジック

発見事項は outputs/manual_audit_11_preliquid.json に保存。
```

## Session 12: PreLiquid Open Application Sale

```
あなたはSolidity監査人です。Legion ProtocolのPreLiquid Open Application Saleを監査してください。

ターゲット: src/sales/LegionPreLiquidOpenApplicationSale.sol

重点チェック:
- Open Application固有のロジック（Approved Saleとの差分）
- 申請→承認フロー中のrace condition
- 承認前に投資できないか
- 申請キャンセル時の状態遷移
- AbstractSaleとの継承関係でのoverride漏れ

発見事項は outputs/manual_audit_12_open_app.json に保存。
```

## Session 13: Fixed Price Sale

```
あなたはSolidity監査人です。Legion ProtocolのFixed Price Saleを監査してください。

ターゲット: src/sales/LegionFixedPriceSale.sol

重点チェック:
- 固定価格計算のオーバーフロー
- maxInvestAmount / minInvestAmount の境界チェック
- 投資上限に達した場合の処理
- AbstractSaleのoverride関数での追加検証の有無
- Fixed Price固有のエッジケース

発見事項は outputs/manual_audit_13_fixed_price.json に保存。
```

## Session 14: CSV Pattern Match — Signature/Nonce Issues

```
あなたはSolidity監査人です。過去のコンテストから署名関連の脆弱性パターンを抽出し、Legion Protocolに適用してください。

Step 1: C:/Users/shieru_k/Documents/security-agent/outputs/legion_similar_issues.csv を読み込む
Step 2: title OR description に signature, replay, nonce, expir, deadline, ecrecover, EIP-712, EIP-1271 を含む行を抽出
Step 3: 各パターンを Legion の以下のファイルに照合:
  - src/position/LegionPositionManager.sol
  - src/sales/LegionPreLiquidApprovedSale.sol (investWithSignature)
  - src/sales/LegionAbstractSale.sol (transferSignature)

Step 4: 一致するパターンがあればPoC概要とともに報告

発見事項は outputs/manual_audit_14_sig_patterns.json に保存。
```

## Session 15: CSV Pattern Match — Token Sale/Launchpad Issues

```
あなたはSolidity監査人です。過去のtoken sale/launchpadコンテストの脆弱性パターンをLegionに適用してください。

Step 1: outputs/legion_similar_issues.csv を読み込む
Step 2: title OR description に claim, vest, tge, alloc, refund, withdraw, supply を含むHigh severity行を抽出（最大100件）
Step 3: 各パターンの攻撃ベクトルを要約
Step 4: Legion の以下に照合:
  - claimTokenAllocation (全実装)
  - supplyTokens
  - withdrawRaisedCapital
  - refund / emergencyWithdraw

発見事項は outputs/manual_audit_15_sale_patterns.json に保存。
```

## Session 16: CSV Pattern Match — Auction Issues

```
あなたはSolidity監査人です。過去のauctionコンテストの脆弱性パターンをLegionに適用してください。

Step 1: outputs/legion_similar_issues.csv を読み込む
Step 2: title OR description に auction, bid, sealed, reveal, settle を含むHigh/Medium行を抽出
Step 3: 各パターンをLegionのSealedBidAuctionSaleに照合
Step 4: 特にfront-running, MEV, bid manipulation, settlement bugs に注目

発見事項は outputs/manual_audit_16_auction_patterns.json に保存。
```

## Session 17: Integer Arithmetic & Precision

```
あなたはSolidity監査人です。Legion Protocol全体の算術演算を監査してください。

ターゲット: src/ 以下全ファイル

重点チェック:
- 除算の丸め方向（プロトコル有利 vs ユーザー有利）
- mulDiv の使用箇所と丸めモード
- TOKEN_ALLOCATION_RATE_DENOMINATOR (1e18?) の使い方
- 大きな値での乗算オーバーフロー
- 小さな値での除算ゼロ
- investedCapital合算時のオーバーフロー（ポジションmerge）
- fee計算で残余ダストが残るケース

発見事項は outputs/manual_audit_17_arithmetic.json に保存。
```

## Session 18: State Transition Integrity

```
あなたはSolidity監査人です。Legion Protocolの状態遷移の整合性を監査してください。

ターゲット: src/ 以下全Sale/Raise実装

重点チェック:
- saleステータスフラグ(isSettled, isCanceled, tokensSupplied, saleEnded等)の遷移グラフを構築
- 矛盾した状態の組み合わせが可能か（例: canceled=true AND tokensSupplied=true）
- pause/unpause中に呼べる関数 vs 呼べない関数の整合性
- cancel後にsupplyTokensを呼べないか
- 時間ベースの条件（startTime, endTime, refundPeriod）の境界条件

状態遷移表を outputs/manual_audit_18_state_transitions.md に保存。
```

## Session 19: Token Distributor & Referrer Fees

```
あなたはSolidity監査人です。Legion Protocolのトークン配布とリファラー報酬を監査してください。

ターゲット:
- src/distribution/LegionTokenDistributor.sol
- src/distribution/LegionReferrerFeeDistributor.sol

重点チェック:
- distribute()の権限チェック
- 配布量とコントラクト残高の整合性
- 二重配布防止
- referrer feeの計算精度
- 0アドレスへの送金
- 配布対象リストの操作可能性

発見事項は outputs/manual_audit_19_distribution.json に保存。
```

## Session 20: Cross-Contract Interaction & Integration Bugs

```
あなたはSolidity監査人です。Legion Protocolのコントラクト間連携を監査してください。

ターゲット: src/ 以下全ファイル

重点チェック:
- Sale → PositionManager → VestingManager → VestingFactory の呼び出しチェーン
- Sale → AddressRegistry の参照整合性
- Factory → Clone → initialize の信頼境界
- external contractへの依存（ERC20 token, Chainlink oracle等）
- コントラクト間でのreentrancy path
- delegatecall の有無と安全性
- selfdestruct / DELEGATECALL / CREATE2 の使用

発見事項は outputs/manual_audit_20_integration.json に保存。
```

---

## 実行手順

1. Claude Code を20セッション開く
2. 各セッションの作業ディレクトリを `C:/Users/shieru_k/Documents/security-agent` に設定
3. 上記プロンプトをそれぞれのセッションにコピペ
4. 全セッション完了後、結果を集約:

```bash
cd C:/Users/shieru_k/Documents/security-agent
python3 -c "
import json, glob
results = []
for f in sorted(glob.glob('outputs/manual_audit_*.json')):
    try:
        data = json.load(open(f, encoding='utf-8'))
        if isinstance(data, list):
            results.extend(data)
        else:
            results.append(data)
    except: pass
print(f'Total findings: {len(results)}')
for r in results:
    sev = r.get('severity', '?')
    title = r.get('title', r.get('finding', '?'))[:80]
    print(f'  [{sev}] {title}')
"
```
