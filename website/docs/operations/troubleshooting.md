---
sidebar_position: 12
---

# トラブルシューティング (手作業リカバリ)

audit pipeline / Web UI / multi-runtime で詰まったときの**手作業での直し方**を症状別にまとめました。目的は「ログ / 状態ファイル / 環境変数のどれを見て、何を編集すれば復帰するか」を明示することです。

:::tip 確認の順番
1. `uv run speca-web` や CLI の **stderr** を最後 50 行眺める
2. `outputs/logs/<phase>_*.jsonl` の最新ファイル末尾を確認
3. `.speca/runs/<run_id>/state.json` で supervisor の認識を確認
4. `outputs/<phase>_PARTIAL_*.json` で何が保存済か確認

ほとんどの問題はこの 4 つを見れば原因が特定できます。
:::

---

## A. 環境セットアップ系

### `uv sync` がエラー

```text
error: Could not find Python 3.12 ...
```

**直し方:**

```bash
uv python install 3.12
uv sync
```

それでも失敗するなら `.venv` を消して再生成:

```bash
rm -rf .venv
uv sync
```

### `npm install` (web/frontend) でハング

Node.js のバージョン不一致が多い。

```bash
node -v        # v20.x 以上か
npm cache clean --force
rm -rf web/frontend/node_modules web/frontend/package-lock.json
cd web/frontend && npm install
```

### `claude` / `codex` / `gemini` / `gh` CLI が見つからない

PATH を確認:

```bash
where claude   # Windows
which claude   # macOS / Linux
```

PATH に通っていない場合の追加 (例: `~/.bashrc` / `~/.zshrc`):

```bash
export PATH="$HOME/.npm-global/bin:$PATH"
```

---

## B. 認証系

### Web UI で `logged_in: false` のままダッシュボードに行けない

**症状:** ブラウザに login 画面が出続ける、`claude auth status --json` は通る。

**原因:** Web 側が見る credentials ファイルパスのズレ。SPECA は `~/.claude/.credentials.json` (**先頭ドット付き**) を一次ソースに、`~/.claude/credentials.json` (ドット無し) をレガシーフォールバックとして読みます。

**確認:**

```bash
ls -la ~/.claude/.credentials.json
cat ~/.claude/.credentials.json | head -c 80   # claudeAiOauth が見えれば OK
```

**手動修復:**

```bash
# 一度ログアウトして再ログイン
claude auth logout
claude auth login
```

それでも直らないなら API key を直接入れる:

```bash
# Web UI の login 画面で ANTHROPIC_API_KEY を貼る
# あるいは
echo '{"apiKey":"sk-ant-..."}' > ~/.claude/credentials.json
```

### Chat パネルで 429 (rate-limited) が出る

**原因:** claude.ai OAuth トークンを Anthropic SDK の API キーとして直叩きすると、subscription routing のスロットルにかかります。

**手動修復:** Web UI ＋ Pro/Max OAuth の組み合わせでは、サーバが自動で `claude` CLI subprocess 経路にフォールバックします (PR #63 で対応済)。それでも 429 が出る場合:

```bash
# 1. 同時並行の claude.exe / claude プロセスを確認 (subscription 並列上限を共有している可能性)
ps -ef | grep claude        # macOS / Linux
tasklist | findstr claude   # Windows

# 2. SPECA が見ている credentials が古い場合は再ログイン
claude auth logout && claude auth login

# 3. それでも 429 → Settings で runtime を ollama / codex に切替
```

### Codex / Gemini で `OPENAI_API_KEY` / `GEMINI_API_KEY` が認識されない

**手動修復:** Web サーバを起動した shell でその env が export 済か確認:

```bash
# Web サーバを起動するシェルで:
echo $OPENAI_API_KEY     # 値が見えるか
echo $GEMINI_API_KEY

# 値が見えるが Settings の availability badge が `!` のまま →
# サーバ起動後に env を変えた場合はサーバ再起動が必要
```

Windows PowerShell:

```powershell
$env:OPENAI_API_KEY = "sk-..."
uv run speca-web --port 7411 --serve-frontend
```

---

## C. Pipeline 実行系

### Phase 01a で「Empty results」

**原因:** `outputs/BUG_BOUNTY_SCOPE.json` が無い / `in_scope` が空 / SPEC_URLS が解決できない。

**確認:**

```bash
cat outputs/BUG_BOUNTY_SCOPE.json
```

期待形:

```json
{
  "url": "https://example.com/bug-bounty",
  "in_scope_assets": ["contracts/MyContract.sol"],
  "spec_urls": ["https://example.com/spec.html"]
}
```

**手動修復:** SPECA を Web UI 経由で起動した場合、`outputs/<run_id>/BUG_BOUNTY_SCOPE.json` も作られます (CLI spec §3.1 `speca init` 相当)。ファイルが空 / 部分的なら以下のいずれか:

```bash
# 1. Web UI の Wizard を再実行
# 2. 直接編集
$EDITOR outputs/BUG_BOUNTY_SCOPE.json

# 3. SPEC_URLS env を上書きして再実行
export SPEC_URLS="https://geth.ethereum.org/docs"
uv run python scripts/run_phase.py --phase 01a --force
```

### Phase 02c で MCP tree-sitter エラー

**症状:** `mcp__tree_sitter__get_symbols` が失敗、code_scope がほとんど空。

**原因:** MCP server が起動していない、または現在の runtime が tree-sitter MCP を使えない (`claude` 以外)。

**確認:**

```bash
# MCP setup
bash scripts/setup_mcp.sh --verify
```

**手動修復:**

```bash
# MCP server を再登録
bash scripts/setup_mcp.sh

# それでも runtime が claude 以外の場合は、02c だけ claude で:
ORCHESTRATOR_RUNNER=claude uv run python scripts/run_phase.py --phase 02c --force

# 残りの phase は別 runtime で:
uv run python scripts/run_phase.py --phase 03 04 --runtime api --force
```

### Phase 03 / 04 で全 batch 失敗

**症状:** circuit breaker tripped (exit 65) / 全 batch が retry exhausted。

**確認:**

```bash
ls -t outputs/logs/03_*.jsonl | head -3
tail -50 outputs/logs/03_W0B0_<latest>.jsonl
```

ログの末尾に `tool_use` ループ / Anthropic API timeout / overload error 等が並んでいるはずです。

**手動修復:**

```bash
# 1. 一時的な API 障害なら force re-run で再開
uv run python scripts/run_phase.py --phase 03 --force --workers 2 --max-concurrent 4

# 2. Prompt 起因なら個別 batch の queue を再生成
rm outputs/03_QUEUE_*.json
uv run python scripts/run_phase.py --phase 03 --force

# 3. 一部 PARTIAL が破損していたら手動削除して resume
rm outputs/03_PARTIAL_W0B5_*.json   # 該当 batch だけ
uv run python scripts/run_phase.py --phase 03
```

### Phase 03 が「BUG_BOUNTY_SCOPE.json missing」で sys.exit

Phase 01e が `outputs/BUG_BOUNTY_SCOPE.json` を必須にしているため。

**手動修復:** `outputs/BUG_BOUNTY_SCOPE.json` を手で配置するか、Phase 01a を先に走らせる。最低限の内容:

```json
{
  "url": null,
  "in_scope_assets": ["src/**/*.sol"],
  "spec_urls": []
}
```

---

## D. Run state 系

### `/api/runs/<id>` が 404 を返す

**症状:** Web UI で「Run not found」、`.speca/runs/<id>/state.json` は存在する。

**原因:** state.json があるが manifest.json が無い run (cancel 等で finalize 前に死んだ)。

**手動修復:** 修正は PR #62 で `state.json` への fallback が入っています。それでも 404 になる場合:

```bash
ls .speca/runs/
ls .speca/runs/<id>/
cat .speca/runs/<id>/state.json | python -m json.tool
```

`run_id` が path と一致しているか確認。不一致なら手動で書き直し:

```bash
python -c "
import json, sys
from pathlib import Path
p = Path('.speca/runs/<id>/state.json')
d = json.loads(p.read_text())
d['run_id'] = '<id>'   # 実際の id に
p.write_text(json.dumps(d, indent=2))
"
```

### 「Orphaned running」run を片付ける

**症状:** Web UI で running 表示のままだが、実際の python プロセスは死んでいる。

**確認:**

```bash
python -c "
import json
from pathlib import Path
for p in Path('.speca/runs').glob('*/state.json'):
    d = json.loads(p.read_text())
    print(p.parent.name, d.get('status'), d.get('owner_pid'))
"
```

`owner_pid` が今のシステムに存在しなければ orphan。Web サーバを再起動すれば自動で `crashed` にリラベルされます (lifespan hook の `reconcile_orphans`)。

**手動修復 (再起動できない場合):**

```bash
python -c "
import json
from pathlib import Path
for p in Path('.speca/runs').glob('*/state.json'):
    d = json.loads(p.read_text())
    if d.get('status') == 'running':
        d['status'] = 'crashed'
        d['cancel_requested'] = True
        p.write_text(json.dumps(d, indent=2))
        print('patched', p.parent.name)
"
```

### `.speca/workspaces/` が肥大化

target 1 つあたり数 GB ある場合があります。

**手動修復:**

```bash
du -sh .speca/workspaces/*
rm -rf .speca/workspaces/<target_slug>
# 次回 run 時に再生成されます
```

---

## E. Web UI 系

### Settings で runtime 切替が効かない

**症状:** Settings でボタンを押しても active 表示が変わらない / chat が以前の runtime で動く。

**確認:**

```bash
curl http://127.0.0.1:7411/api/runtime
cat ~/.speca/runtime.json
```

両方が一致していて、かつ Chat で送信した後の SSE で当該 runtime の動作が観測できるか:

```bash
# 直接 SSE を叩いて runtime 動作を観測
CID=$(python -c "import uuid; print(uuid.uuid4())")
curl -N -X POST http://127.0.0.1:7411/api/chat/conversations/$CID/messages \
  -H "Content-Type: application/json" \
  -d '{"text":"hello"}'
```

**手動修復:**

```bash
# 設定ファイルを直接編集
cat > ~/.speca/runtime.json <<'EOF'
{
  "runtime": "ollama",
  "ollama_host": "http://localhost:11434",
  "ollama_model": "llama3.2"
}
EOF

# Web サーバを再起動 (Settings ロードは load() が再読み込みなので不要だが念のため)
```

### Chat パネルで SSE が parse されない / 表示が空

**症状:** メッセージを送信しても何も出ない、Network タブで SSE は流れている。

**原因 (PR #62 / #63 で修正済):** Windows の sse-starlette は frame を `\r\n\r\n` で区切るのに対し、SPA の parser が `\n\n` だけを見ていた。

**確認:**

```bash
# SSE の生バイトを確認
CID=$(python -c "import uuid; print(uuid.uuid4())")
curl -N -X POST http://127.0.0.1:7411/api/chat/conversations/$CID/messages \
  -H "Content-Type: application/json" \
  -d '{"text":"hi"}' | xxd | head -10
```

`0d 0a 0d 0a` (CRLF CRLF) で区切られていれば CRLF。dev に PR #62 がマージ済なら修正済。

**手動修復:** `web/frontend/src/features/chat/useChatStream.ts` の SSE parser が CRLF → LF 正規化を持っているか:

```typescript
buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
```

無ければ追加して `npm run build`。

### 既存 chat 履歴が消えた

**確認:**

```bash
ls ~/.speca/chat/ 2>/dev/null || ls .speca/chat/
```

**手動修復:** conversation ファイルは plain JSON なので外部から復元可能:

```json
{
  "conversation_id": "...",
  "messages": [
    {"role":"user","content":[{"type":"text","text":"..."}],"timestamp":"2026-05-15T..."},
    {"role":"assistant","content":[{"type":"text","text":"..."}],"timestamp":"2026-05-15T..."}
  ],
  "created_at": "...",
  "last_message_at": "..."
}
```

---

## F. Multi-runtime 特有

### `--runtime codex` で exit 2 になる

```text
ERROR: runtime 'codex' cannot drive the orchestrator.
```

**原因:** PR #67 がまだ dev にマージされていない時点では codex / gemini / ollama は orchestrator 側 stub。

**手動修復:** `--list-runtimes` で `(stub)` ラベルが消えるまで待つか、`api` runtime を OpenAI 互換エンドポイントで代用:

```bash
export API_RUNNER_API_KEY=$OPENAI_API_KEY
export API_RUNNER_BASE_URL=https://api.openai.com/v1
export API_RUNNER_MODEL=gpt-4o
uv run python scripts/run_phase.py --target 04 --runtime api
```

### Ollama self-hosted が応答しない

```bash
curl http://localhost:11434/api/tags
# モデル一覧が出るか
```

出ない場合:

```bash
ollama serve &      # 別ターミナルで
ollama pull llama3.2
```

`/v1/chat/completions` の OpenAI 互換 endpoint も別途確認:

```bash
curl http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.2","messages":[{"role":"user","content":"hi"}]}'
```

---

## G. アーカイブ / 再現性

### `.speca/runs/<id>/` の中身を見たい

```bash
tree .speca/runs/<id>/
cat .speca/runs/<id>/manifest.json | python -m json.tool
ls .speca/runs/<id>/phases/
```

`manifest.json` には commit SHA / env snapshot / spec sources / runtime が記録されているので、別環境で同じ条件を再現する場合の指針になります。

### 過去 run を別マシンで再現したい

```bash
# 1. アーカイブを tarball にして転送
tar czf run-<id>.tar.gz .speca/runs/<id>/ outputs/<id>/

# 2. 別マシンで展開
tar xzf run-<id>.tar.gz

# 3. manifest の env_snapshot を読んで同じ env を export
python -c "
import json
m = json.load(open('.speca/runs/<id>/manifest.json'))
for k, v in m['env_snapshot'].items():
    print(f'export {k}={v}')
"

# 4. 同じ commit SHA + runtime で再実行
git checkout <sha>
ORCHESTRATOR_RUNNER=<runtime> uv run python scripts/run_phase.py --phase 03 04 --force
```

---

## H. 最後の砦

どうしようもないとき:

```bash
# 1. 状態を全部消す (run / chat / workspace / runtime 設定すべて)
rm -rf .speca/ ~/.speca/
rm -rf outputs/

# 2. credentials も初期化したい場合
rm ~/.claude/.credentials.json ~/.claude/credentials.json 2>/dev/null
claude auth login

# 3. 依存も入れ直す
rm -rf .venv web/frontend/node_modules
uv sync
cd web/frontend && npm install && cd ../..
```

それでもダメなら [GitHub Issues](https://github.com/NyxFoundation/speca/issues) に再現手順を貼ってください。

## ログ / 状態ファイル 一覧

| パス | 何が入っているか |
|---|---|
| `outputs/logs/<phase>_W<W>B<B>_<ts>.jsonl` | claude CLI / API runner の stream-json log。tool_use 履歴、cost、error 全部 |
| `outputs/<phase>_PARTIAL_W<W>B<B>_<ts>.json` | 各 batch の処理結果 (resume の入力) |
| `outputs/<phase>_QUEUE_<worker>.json` | per-worker の処理待ち queue |
| `.speca/runs/<id>/state.json` | Web supervisor の認識する run 状態 (status / owner_pid / phases / cancel_requested / max_budget_usd) |
| `.speca/runs/<id>/manifest.json` | run の不変メタ (commit SHA / env snapshot / spec sources / 採用 runtime) |
| `.speca/workspaces/<target_slug>/` | target repo の bare cache + worktree |
| `~/.speca/runtime.json` | Web UI の runtime 選好 |
| `~/.speca/chat/<conversation_id>.json` | Chat 履歴 |
| `~/.claude/.credentials.json` | claude CLI の OAuth トークン (秘密) |
| `~/.claude/credentials.json` | レガシー API key 保存先 |
