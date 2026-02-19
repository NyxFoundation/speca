# Claude Code コスト/コンテキスト最適化メモ

目的: Phase-03 ワークフローで観測された `cache_read_input_tokens` の肥大 (>99% を占有) を抑え、トークン課金を削減する。

## 価格モデルの要点
- キャッシュ書き込み: 基本入力単価の 1.25x (5分) / 2x (1時間)。
- キャッシュ読み出し: 基本入力単価の 0.1x (90% 引き)。
- 200K input 超のリクエストは長大コンテキスト料金 (Sonnet 4.5: 入力 6$/M, 出力 22.5$/M)。
- キャッシュ対象は `tools`→`system`→`messages` のプレフィクス全体。

## なぜ cache_read が膨らむか (原理)
1. Claude は各ターンで「これまでの全履歴」を再ロードする。履歴が長文 (前ターンの result 4–5万 tok + 手順全文) だと、再読コストがターン数に比例して積み上がる。
2. 長いチェックリスト/プロンプトを毎ターン送ると、それが毎回 cache_read に乗る。
3. ツール出力をそのまま会話に残すと、以降のターンでも全文がコンテキストに含まれる。

## 設計指針 (実装に落とす)
### 1) セッション/ターン設計
- 1ワーカー = 1〜3ターンで完結。大きな result を出したら会話を終了し、新セッションを開始して履歴をリセット。

### 2) コンテキスト分離
- チェックリスト・共通手順・ルールは **一度だけキャッシュ書き込み** し、以降のターンでは差分だけ送る。
- 大きなツール結果はファイルに書き出し、次ターンでは必要な数行の要約だけを送る。

### 3) フィールド最小化 (すでに実施済み)
- result は `id, classification, code_path, proof_trace, attack_scenario, checklist_id` の6フィールドに限定。出力自体を小さくし、再読サイズを減らす。

### 4) 長大入力のガード
- `input + cache_creation + cache_read` 合計が 200K を超えないよう、ターン毎に推定。超えそうならセッション分割。

### 5) キャッシュ活用の型
- 変更されないシステムプロンプト・ツール定義・長い規約は `cache_control` 付きで先に送る（書き込みは1.25xでも、以降は0.1xで読み出し）。
- 変動する部分（バッチID、ファイルパス等）のみ通常入力で送る。

### 6) ツール/モデル設定
- 不要な MCP サーバやツール宣言は削除し、初期コンテキストを圧縮。
- 大きなコードを貼る場合は `head/tail` 抜粋と行番号のみ。

## 運用チェックリスト
- [ ] 1ターンあたりの想定 context を計算し、200K 閾値を跨がないか確認
- [ ] 共有プロンプトはキャッシュに載せたか
- [ ] ツール結果はファイル保管＋要約転記にしているか
- [ ] 余分なヘッダ/一覧/推奨文を result に含めていないか
- [ ] セッションを跨ぐときは履歴を持ち越していないか

## ログからの実例 (Phase-03)
- `outputs/logs/03_w3b4_1771330069.log.jsonl` 行65  
  - cache_read_input_tokens: **1,611,473**  
  - output_tokens: **52,052**  
  - ターン数: 27  
  - 原因: 長大resultを出した後も会話を継続し、全履歴を再読。
- `outputs/logs/03_w1b2_1771324131.log.jsonl` 行90  
  - cache_read_input_tokens: **1,429,625**  
  - output_tokens: **43,269**  
  - ターン数: 26  
  - 原因: チェックリスト長文＋複数ファイル解析を数ターンに分割。
- 全03ログ合計 (193ファイル):  
  - input_tokens 9,851 / output_tokens 1,897,589 に対し cache_read 432,552,689 (≈99.5%).

## 参考ソース
- Prompt caching 1.25x/2x/0.1x 価格表: [Claude Docs Pricing](https://docs.claude.com/en/docs/about-claude/pricing)
- 長大コンテキスト (>200K) プレミアム課金 (Sonnet 4.5: 6$/M in, 22.5$/M out): [Platform Pricing – Long context](https://platform.claude.com/docs/en/about-claude/pricing)
- キャッシュ対象は tools→system→messages 全体: [AIHubMix Cache doc](https://docs.aihubmix.com/en/api/Claude-Cache)
