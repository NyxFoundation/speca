---
sidebar_position: 2.5
---

# Web UI クイックスタート (5 分)

ブラウザだけで初回監査を回すクイックスタート。CLI 版は [こちら](./quickstart.md)、フル機能ツアーは [Web UI ガイド](../guide/web-ui.md) を参照してください。

## 0. 前提

- Node.js 20+ / Python 3.12 (`uv`) / git が入っていること
- [インストール](./installation.md) が完了していること

事前確認:

```bash
node --version
uv --version
```

## 1. 認証 (1 度だけ)

3 つの方法のいずれか:

```bash
# A. Claude Pro/Max サブスクリプション (推奨)
npm install -g @anthropic-ai/claude-code
claude auth login        # ブラウザで claude.ai OAuth

# B. Anthropic API key
export ANTHROPIC_API_KEY=sk-ant-api-...

# C. Web UI から後で入れる (login 画面で paste)
```

確認:

```bash
claude auth status --json
```

## 2. Web サーバ起動

```bash
uv run speca-web --port 7411 --host 127.0.0.1 --serve-frontend
```

ブラウザで http://127.0.0.1:7411/ を開く:

![Dashboard](/img/web-ui/01_dashboard_default.png)

未ログインなら paste-code OAuth or API key 入力画面が出ます。

## 3. 新規 run を Wizard から起動

ダッシュボードの **+ 新規 run** から `/runs/new/wizard` へ:

1. **プロジェクト種別** — `smart_contract` 等
2. **対象リポジトリ** — `owner/name` (例: `OpenZeppelin/openzeppelin-contracts`)
3. **対象 ref** — 空欄 = デフォルトブランチ
4. **スコープ** — Bug bounty URL があれば貼る
5. **Spec URLs** — オプション (Phase 01a の seed)
6. **Confirm** — Launch

エラー時は [9 ケースのモーダル](../operations/web-ui-features.md#error-handling) で対処が表示されます。

## 4. 進捗を眺める

![Run detail with phases](/img/web-ui/05_run_detail_budget_phases.png)

phase 行をクリックで展開、または focus 中に `l` でログペインへ scroll、`f` で当該 phase のみ force re-run。

予算が気になるなら **ゲージをクリック** → cap-bump モーダルで上限を上げる:

![Cap-bump modal](/img/web-ui/06_budget_cap_bump_modal.png)

## 5. Findings を見る

監査が完了すると `/runs/<id>/findings` に findings 一覧。DSL filter / Markdown export / Prism コードハイライト全部使えます:

![Findings list](/img/web-ui/03_findings_list.png)

![Finding detail with code highlight](/img/web-ui/04_finding_detail_code_highlight.png)

## 6. Chat パネルで個別質問

行詳細の **Ask Claude about this finding** ボタンで Chat に finding を inject。または右上の Chat ボタン / `c` キーで開いてフリーフォームで:

![Chat panel](/img/web-ui/07_chat_panel_empty.png)

## (オプション) 別 runtime を試す

`/settings` の **Chat runtime** セクション で claude 以外も選べます:

![Runtime selector](/img/web-ui/11_runtime_selector.png)

| Runtime | 認証 |
|---|---|
| **Claude** (既定) | `claude auth login` or `ANTHROPIC_API_KEY` |
| **Codex** | `codex login` (ChatGPT plan) or `OPENAI_API_KEY` |
| **Gemini** | `GEMINI_API_KEY` or Google ADC (`gcloud auth application-default login` + `GOOGLE_GENAI_USE_GCA=true`) |
| **Ollama** | self-hosted (`OLLAMA_HOST=http://localhost:11434`) or cloud (+ `OLLAMA_API_KEY`) |
| **Copilot** | `gh auth login` + Copilot 契約 (Chat のみ) |

availability badge `✓` / `!` で各 runtime が今すぐ使えるかが一目で分かります。env を export してから Web サーバ再起動が確実。詳細は [Multi-runtime バックエンド](../operations/multi-runtime.md)。

:::info Chat / Audit OAuth ギャップ
**Chat パネル**は CLI subprocess を経由するので、OAuth (codex login / ChatGPT plan / Google ADC) と API key 両方使えます。
**Audit pipeline 側**は OpenAI 互換 API を直接叩くので、現状 API key が必須です (`OPENAI_API_KEY` / `GEMINI_API_KEY`)。
:::

## (オプション) UI のカスタマイズ

ヘッダから:
- **L / D / A / S** — Light / Dark / Auto / **Solarized** テーマ切替
- **EN / JA** — 言語切替

![Theme toggle](/img/web-ui/09_settings_theme_4buttons.png)

## トラブル時は

- 一覧: [トラブルシューティング](../operations/troubleshooting.md)
- ショートカット: `?` キーで help モーダル

![Keyboard shortcuts](/img/web-ui/08_keyboard_shortcuts_help.png)

## 次のステップ

- [Web UI 機能の全体](../operations/web-ui-features.md)
- [Multi-runtime バックエンド](../operations/multi-runtime.md)
- [CLI でも同じことをする](./quickstart.md)
- [CLI リファレンス](./cli-reference.md)
