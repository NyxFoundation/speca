あなたは Current Finance (Sherlock #1256) 監査レポートの重複チェック担当です。
複数エージェントがマージされた後の outputs/reports/ を精査し、重複レポートの整理を行ってください。

## セットアップ

cd /Users/hiro/Documents/security-agent
git fetch origin
git checkout hiro/elegant-wiles
git pull origin hiro/elegant-wiles

## 手順

1. outputs/reports/ の全レポートを読む

2. 重複判定:
   以下の基準で重複を判定する:
   - 同じ根本原因 (同じファイル:同じ行番号) を指摘している
   - 同じ攻撃シナリオを説明している
   - 同じ修正案を提示している
   上記のいずれか 2 つ以上が一致すれば重複とみなす

3. 重複が見つかった場合の対応:
   A. 内容がより詳しい方を残す (コードスニペットが多い、影響範囲が広い、修正案が具体的)
   B. 残す方のレポートに、消す方の独自の知見があれば追記する:
      - 追加の攻撃シナリオ
      - 追加のコード箇所
      - 追加の影響分析
      - 独立確認の事実 ("Independently confirmed by N agents" 等)
   C. 消す方のレポートファイルを git rm する

4. 番号の再採番:
   重複削除後、レポート番号に欠番ができる場合は git mv でリネームして連番にする:
   report_001, report_002, ... report_NNN が連番になるようにする

5. 重複チェック結果のサマリーを outputs/reports/DEDUP_LOG.md に記録:

# 重複チェックログ

## 実行日時
<日時>

## 統合されたレポート
| 残したレポート | 削除したレポート | 理由 |
|-------------|--------------|------|
| report_003 | report_028 | 同じ root cause (market.move:745) |

## 追記された内容
| レポート | 追記内容 |
|---------|---------|
| report_003 | agent-5 による独立確認を追記 |

## 最終レポート数
<整理後の総数>

6. コミット:
   git add outputs/reports/
   git commit -m "chore: dedup reports - merged N duplicates, final count: M reports"
   git push origin hiro/elegant-wiles
