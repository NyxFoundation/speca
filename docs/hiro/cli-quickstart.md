# speca-cli クイックスタート (hirorogo team 向け 5 分ガイド)

> **対象:** speca-cli (TUI front-end) を初めて触る hirorogo team メンバー
> **OS 前提:** Windows 11 (PowerShell 5.1 / WSL2 どちらでも可)
> **対象バージョン:** `speca-cli@0.1.0-alpha.0` (M2 preview)
> **完成度:** `version` / `doctor` / `auth` / `init` まで動く。`run` / `browse` は M3 以降 (coming soon)。

speca 本体 (Python オーケストレータ) を直接叩く場合の手順は [root README "Quick Start"](../../README.md#quick-start) を参照。本ガイドはそれを TUI でラップした `speca-cli` の使い方のみを扱う。

## 0. 事前準備 (既にあるもの確認)

| 必要なもの | 確認 | 入っていない場合 |
|------------|------|------------------|
| Node.js 20+ | `node --version` | https://nodejs.org/ から LTS |
| git | `git --version` | https://git-scm.com/downloads |
| uv | `uv --version` | `pip install uv` (要 Python 3.8+) |
| Claude Pro/Max サブスク | — | https://claude.ai/ (API key 代替可) |

Claude Code CLI (`npm install -g @anthropic-ai/claude-code`) は M5+ の chat pane で必要だが今は不要。

## 1. doctor で環境チェック (1 分)

```powershell
npx speca-cli@next doctor
```

`-g` でインストールしたくない場合はそのまま `npx` で OK。出力例:

```text
[OK] node     v20.18.1
[OK] uv       uv 0.4.20
[OK] git      git version 2.43.0
[OK] claude   2.1.87
```

すべて `[OK]` であれば次へ。`[FAIL]` が出たらその行に書かれているインストール手順に従う。

## 2. サブスクリプション認証 (2 分)

```powershell
npx speca-cli@next auth login
```

ブラウザが開き Claude Code OAuth 同意画面が表示される。サインイン後にコード文字列が画面に出るのでそれをコピーして CLI のプロンプトに貼り付ける。

```text
We've opened the following URL in your browser:

  https://claude.ai/oauth/authorize?client_id=...&scope=user:sessions:claude_code...

After signing in, claude.ai will redirect you to a page that shows
a code. Paste the entire string below.

> Paste code: <ここに貼る>

[OK] Signed in via Claude Code subscription.
     Account: you@example.com
     Scope:   org:create_api_key user:profile user:inference
              user:sessions:claude_code user:mcp_servers user:file_upload
```

`user:sessions:claude_code` scope が含まれていれば成功 (この scope がサブスクリプション課金の鍵)。

確認:

```powershell
npx speca-cli@next auth status
```

> **API key で代替したい場合 (CI / サブスクなしの人):**
> ```powershell
> $env:ANTHROPIC_API_KEY = "sk-ant-..."
> npx speca-cli@next auth login --api-key
> ```

トークン保存先: `~/.config/speca/auth.json` (`chmod 0o600`、Windows でも同等の ACL が付く)。

## 3. プロジェクト初期化 (2 分)

監査対象ごとにフォルダを切る。

```powershell
mkdir audits\my-target
cd audits\my-target
npx speca-cli@next init
```

ウィザードが順に聞いてくる:

| Step | 質問 | 例 |
|------|------|-----|
| 1 | Project name | `my-target` |
| 2 | Target git URL | `https://github.com/sigp/lighthouse` |
| 3 | Pin commit? | Enter (HEAD のまま) もしくはコミットハッシュ |
| 4 | Specification source(s) | `https://github.com/ethereum/EIPs/blob/master/EIPS/eip-7594.md` (複数行可) |
| 5 | Bug-bounty scope | `ethereum-consensus` などのテンプレを選択 |
| 6 | Audit budget (USD) | `10` |

完了すると以下が生成される:

```text
my-target\
├── outputs\
│   ├── TARGET_INFO.json
│   └── BUG_BOUNTY_SCOPE.json
└── .speca\
    ├── session.json
    └── prefs.json
```

`.speca\` は `.gitignore` 推奨。

## 4. パイプライン実行 (coming soon — M3)

`speca run` は M3 でリリース予定 (現在 0.1.0-alpha.0 では未実装)。

```powershell
# 予定 (M3+)
speca run --target 04 --workers 4
```

それまでは Python オーケストレータを直接叩く:

```powershell
# speca リポジトリ本体を別フォルダに clone してそこから
uv run python3 scripts\run_phase.py --target 04 --workers 4
```

## 5. 結果ブラウズ (coming soon — M4)

`speca browse` は M4 でリリース予定。それまでは `outputs\04_PARTIAL_*.json` を直接読むか `jq` / `ConvertFrom-Json` で整形する。

## Windows ハマりどころ

| 症状 | 対処 |
|------|------|
| `npx` で `EPERM: operation not permitted` (`node-pty` 展開時) | 初回だけ管理者権限で PowerShell を開いて再実行。または `$env:npm_config_build_from_source = "false"` |
| `auth login` のブラウザで別アカウントに飛ぶ | InPrivate ウィンドウで開き直し、目的の Claude アカウントでサインイン |
| `init` 後の JSON が CRLF + BOM で orchestrator が読めない | エディタを UTF-8 (BOM なし) / LF に設定。`speca init` 自体は LF で書く |
| WSL2 と Windows 側パスの混在で `outputs\TARGET_INFO.json` が見つからない | `speca` を一つのシェルから実行統一。混ぜたい場合は `speca -C "$(wslpath /mnt/c/audits/my-target)"` |
| `auth status` で `scope missing user:sessions:claude_code` | 過去のトークンが別 OAuth client で発行されている。`speca auth login` を再実行 |

## 関連ドキュメント

- [`cli/README.md`](../../cli/README.md) — speca-cli の英語版フルドキュメント (全コマンド + 全 troubleshooting)
- [`docs/SPECA_CLI_SPEC.md`](../SPECA_CLI_SPEC.md) — 設計仕様 (M1 〜 M7 の全機能)
- [`README.md`](../../README.md) — speca 本体 (Python pipeline) の使い方
- Tracking issue: [NyxFoundation/speca#3](https://github.com/NyxFoundation/speca/issues/3)

## 困ったとき

`speca doctor` の出力 + `speca version` を添えて [Issue を立てる](https://github.com/NyxFoundation/speca/issues/new) か、hirorogo team の Slack に投げる。
