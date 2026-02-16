---
name: Bug report
about: バグ報告（OpenHandsで再現→修正→テストまで回しやすい形式）
title: "[Bug] "
labels: ["bug"]
assignees: ""
---

## 概要
（何が起きているかを1〜2行で）

## 再現手順
1.
2.
3. 失敗するコマンド：
   ```bash
   uv run python -m pytest
````

## 期待する挙動

（どうなればOKか）

## 現状の挙動（ログ/エラー）

`uv run python -m pytest` の出力（最後20行くらい）を貼ってください。

```text
（ここにログ）
```

## 受け入れ条件

* [ ] `uv run python -m pytest` が成功する（exit code 0）
* [ ] 必要ならテスト追加/更新が含まれる
* [ ] 変更理由がPR説明に書かれている

## OpenHandsへの指示

@openhands-agent

* 必ず実コード変更を含めて修正してください（差分0だとPR作成が失敗します）。
* 修正後に `uv run python -m pytest` を実行して通ることを確認してください。
* コード変更が不要と判断した場合は、その理由と代替案をIssueにコメントしてください。
