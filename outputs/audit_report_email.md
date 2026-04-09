愛知教育委員会の関連Webサイト及びサービスにおいて、外部から認証不要で悪用可能な重大なセキュリティ上の問題を複数発見いたしました。特に、貴校ドメインを騙ったなりすましメールの送信が技術的に可能な状態であり、生徒・保護者・教職員へのフィッシング被害が発生するリスクが極めて高い状況です。

本件は情報セキュリティご担当者様またはシステム管理ご担当者様へ早急に共有いただけますよう、お願い申し上げます。

以下、検出した脆弱性の詳細をご報告いたします。

---

## 基本情報

| 項目 | 内容 |
|------|------|
| 対象 | 愛知県立愛知総合工科高等学校 関連ドメイン |
| 対象ドメイン | aichi-te.aichi-c.ed.jp, aichi-te-ad.jp, aichi-te-ad.webclass.jp, www.aichi-te-ad.jp 他 |
| 調査実施日 | 2026年4月8日〜9日 |
| 調査手法 | 外部からのパッシブ偵察・API分析・DNS分析・技術検証 |
| 報告者 | 村上大岳 |

---

## 概要

外部（インターネット側）から認証情報なしでアクセス可能な脆弱性を中心に調査を実施しました。
合計28件の脆弱性を検出し、うち13件は認証不要で外部から悪用可能な状態です。
特に深刻な問題として、WebClass LMSの管理者情報漏洩、メールスプーフィング、
セッションフラッディングDoSが理論上可能であることを確認いたしました。

| 深刻度 | 件数 |
|--------|------|
| Critical | 1件 |
| High | 5件 |
| Medium | 16件 |
| Low | 5件 |
| Informational | 1件 |

---

## 検出脆弱性一覧

### 認証不要・外部から即時悪用可能 (EXT)

| ID | 深刻度 | タイトル | 状態 |
|----|--------|---------|------|
| EXT-001 | **High** | WebClass Session Flooding DoS（レート制限なし） | 技術検証済 |
| EXT-002 | **High** | WebClass 公開APIによる管理者情報漏洩 | 技術検証済 |
| EXT-003 | **High** | メールスプーフィング（DMARC/SPF不備） | 技術検証済 |
| EXT-007 | **High** | メールサービス平文認証の公開（IMAP/POP3） | 技術検証済 |
| EXT-004 | Medium | SSLStripping（HSTS未設定 + HTTP自己リンク） | 確認済 |
| EXT-005 | Medium | WebClass セッションCookie属性欠落 | 技術検証済 |
| EXT-006 | Medium | WebClass ブルートフォース無制限 | 技術検証済 |
| EXT-008 | Medium | FTPサーバー公開 + バージョン情報露出 | 技術検証済 |
| EXT-009 | Medium | WebClass 公開APIによる教育運用データ漏洩 | 技術検証済 |
| EXT-011 | Medium | a-blog cms 管理者ログイン公開 + ユーザー列挙 | 技術検証済 |
| EXT-012 | Medium | Scrapbox API 全コンテンツ認証不要取得 | 技術検証済 |
| EXT-013 | Medium | AWSELB Cookie オリジンサーバーIP漏洩 | 技術検証済 |
| EXT-010 | Low | WebClass 公開投稿のIDOR（連番ID列挙） | 確認済 |

### 認証取得後の攻撃チェーン (EXP)

| ID | 深刻度 | タイトル |
|----|--------|---------|
| EXP-001 | **Critical** | WebClass Stored XSS → セッション窃取チェーン |
| EXP-002 | **High** | WebClass セッションID生成の脆弱性 |

### 設定・ヘッダ不備 (F)

| ID | 深刻度 | タイトル |
|----|--------|---------|
| F-001〜003 | Medium | WebClass Cookie/CSRF/ブルートフォース |
| F-004〜006 | Medium | DMARC/SPF設定不備 |
| F-007〜008 | Medium | HSTS/CSP未設定 |
| F-009〜010 | Medium | WordPress未更新 / TLS 1.2のみ |
| F-011〜014 | Low | 情報露出 / DNS管理分離 |
| F-015 | Info | note.jpトークン露出 |

---

## High以上の脆弱性 詳細

### EXT-001: WebClass Session Flooding DoS [High]

**概要:** WebClassログインページ(`/webclass/login.php`)へのGETリクエスト毎にサーバーサイドでセッションが生成され、レート制限が一切ない。

**技術検証結果:**
```
対象: https://aichi-te-ad.webclass.jp/webclass/login.php
レート制限の欠如を確認
リクエスト毎に一意なセッションIDが生成されることを確認
```

レート制限が存在しないため、理論上、大量のリクエストによりセッションストアを枯渇させ、正規ユーザーのログインを妨害可能。EXT-013のオリジンIP経由ではCloudFrontのDDoS防御もバイパスされる可能性がある。

**推奨対策:** セッション生成のレート制限導入。既存セッションの再利用。IP単位のアクセス制限。

---

### EXT-002: WebClass 公開APIによる管理者情報漏洩 [High]

**概要:** 認証不要のAPIエンドポイントが管理者のユーザー名・実名・権限・内部IDを返却する。

**技術検証結果:**
```
エンドポイント: /webclass/information.php/public/api/listForGuest

取得可能なデータ:
  管理者ユーザー名・実名・権限・内部IDが認証不要で取得可能
```

この情報はEXT-006（ブルートフォース）やEXT-003（メールスプーフィング）と組み合わせた場合、攻撃精度を大幅に向上させる可能性がある。

**推奨対策:** APIレスポンスから管理者の内部情報（ユーザー名・ID・権限・実名）を除外。

---

### EXT-003: メールスプーフィング [High]

**概要:** aichi-te.aichi-c.ed.jpにDMARCレコードが存在せず、SPFもsoft fail(~all)のため、学校ドメインを騙ったなりすましメール送信が技術的に可能な状態。

**DNS検証結果:**
```
aichi-te.aichi-c.ed.jp:
  DMARC: レコードなし
  SPF:   v=spf1 +ip4:210.162.58.204 ~all（soft fail = 拒否しない）

aichi-te-ad.jp:
  DMARC: v=DMARC1; p=none（監視のみ、rua未設定）
  SPF:   v=spf1 ... ~all（soft fail = 拒否しない）
```

**リスク:**
DMARCレコードが存在しないため、貴校ドメインを騙ったなりすましメールが技術的に送信可能であり、受信側で拒否する仕組みがない状態です。また、偽装メール送信の記録すら残りません。

**想定される攻撃シナリオ:**
1. EXT-002で取得可能な管理者ユーザー名を利用
2. 貴校ドメインとして教職員・保護者にフィッシングメールを送信
3. DMARCなし + SPF soft failのため受信側メールサーバーは拒否しない
4. WebClass偽装ログインページに誘導し認証情報を窃取

**推奨対策:**
- DMARCポリシーを `p=reject` に設定（両ドメイン）
- SPFを `-all` (hard fail) に変更
- DKIMの導入と署名の有効化
- DMARCレポート受信アドレス(rua)の設定

---

### EXT-007: メールサービス平文認証の公開 [High]

**概要:** aichi-te-ad.jpのメールサーバー(210.154.252.239)がインターネットに公開されており、STARTTLS前にAUTH=PLAINを提供している。

**技術検証結果:**
```
IMAP (143): STARTTLS前にAUTH=PLAIN AUTH=LOGINを提供
POP3 (110): SASL PLAIN LOGIN を提供
SMTP (587): AUTH PLAIN LOGIN を提供
FTP  (21):  vsFTPd 3.0.3 が応答
```

メールクライアントがSTARTTLSを使用しない設定の場合、教職員のメール認証情報が平文で送信される可能性がある。

**推奨対策:** STARTTLS前のAUTH=PLAINメカニズムを無効化。IMAP(993)/POP3(995)のSSL/TLSのみ許可。

---

### EXP-001: WebClass Stored XSS → セッション窃取チェーン [Critical]

**概要:** 以下の脆弱性を連鎖させることで、認証情報なしの状態から全ユーザーのセッション窃取まで理論上到達可能。

**想定される攻撃チェーン:**
1. **EXT-002**: 公開APIで管理者ユーザー名を取得（認証不要）
2. **EXT-006**: CAPTCHA/レート制限/ロックアウトなしのためブルートフォースが理論上可能
3. **Stored XSS**: 管理者権限で「お知らせ」にXSSペイロードを投稿可能。APIの`format`フィールドが`legacy-html`のため、HTMLがそのまま格納・配信される構造。フロントエンドのJavaScriptは`jQuery.append()`でAPIレスポンスをサニタイズなしでDOM挿入。
4. **セッション窃取**: `WBT_Session`CookieにHttpOnly属性がないため、`document.cookie`で読み取り可能な状態。

**想定される影響:** 学生・教職員のWebClassアカウント乗っ取り。成績データ・出席情報・課題提出物の閲覧・改ざんの可能性。

---

## Medium脆弱性 詳細

### EXT-004: SSLStripping [Medium]

メインサイト(aichi-te.aichi-c.ed.jp)と附属中学校サイト(aichi-te-jh.aichi-c.ed.jp)にHSTSヘッダがなく、HTML内にhttp://自サイトへのリンクが存在。校内Wi-Fi上でのSSLStripping攻撃が理論上可能。

### EXT-005: セッションCookie属性欠落 [Medium]

セッションCookieにSecure, HttpOnly, SameSite属性が全て欠落していることを確認。path scopeも`/`と広い。

### EXT-006: ブルートフォース無制限 [Medium]

管理者ユーザー名がEXT-002で取得可能な状態で、ログインフォームにCAPTCHA・レート制限・ロックアウト・CSRFトークンが一切なし。レート制限・ロックアウト機構の不在を確認。

### EXT-008: FTPサーバー公開 [Medium]

vsFTPd 3.0.3（2015年リリース）がインターネットに公開。FTPプロトコルは認証情報を平文で送信する仕様。

### EXT-009: 教育運用データ漏洩 [Medium]

公開APIから認証不要で以下の種類の情報が取得可能な状態:
- コース名・教室変更・オンデマンド授業への切替情報
- 授業時間・施設利用情報
- 内部ネットワーク情報（Wi-Fi名、プリンタ設置情報等）

### EXT-011: a-blog cms管理者ログイン公開 + ユーザー列挙 [Medium]

```
ログインページ:     /login/ (CAPTCHAなし、公開状態)
パスワードリセット: /admin-reset-password/ (公開状態)
ユーザー列挙:       パスワードリセットフォームでユーザー存在確認が可能
CMS:               a-blog cms (standard edition)
```

### EXT-012: Scrapbox API全コンテンツ認証不要取得 [Medium]

```
複数のScrapboxプロジェクトにおいて、全ページの内容が認証不要で取得可能な状態
公開設定: publicVisible=true
```

### EXT-013: AWSELB Cookie オリジンIP漏洩 [Medium]

```
AWSELB Cookieからオリジンサーバーの内部IPアドレスがデコード可能
→ CloudFrontのDDoS防御・WAF・レート制限のバイパスに利用される可能性がある
```

---

## 対策推奨事項（優先度順）

### 即時対応が必要な項目

1. **[最優先] DMARC/SPF/DKIM修正（EXT-003）** --- DMARCをp=rejectに、SPFを-allに、DKIM導入。**現状、学校ドメインを騙ったフィッシングメールが技術的に送信可能な状態であり、受信側で検知・拒否する仕組みがない。** 生徒・保護者・教職員が被害対象となる可能性があり、悪用に高度な技術スキルは不要。DMARCレコードが存在しないため、偽装メール送信の記録すら残らない。
2. **WebClass listForGuest API修正** --- APIレスポンスから管理者情報を除外（EXT-002）。管理者の情報が公開されていることでEXT-003のフィッシング精度が向上する可能性がある。
3. **WebClass セッションCookie修正** --- Secure/HttpOnly/SameSite=Strict追加（EXT-005）
4. **WebClass ログイン保護** --- CAPTCHA + レート制限 + CSRFトークン導入（EXT-006）
5. **メールサーバー設定修正** --- STARTTLS前のAUTH=PLAIN無効化（EXT-007）
6. **WebClass XSS対策** --- お知らせHTMLのサニタイゼーション（EXP-001）

### 短期対応が必要な項目

7. WebClass セッション生成にレート制限導入（EXT-001）
8. AWSELB cookie無効化またはオリジンIP保護（EXT-013）
9. HSTS導入（EXT-004）
10. CSP導入（F-008）
11. a-blog cms ログインページへのIP制限 + CAPTCHA（EXT-011）
12. FTPサーバー停止またはSFTP移行（EXT-008）

### 中長期対応

13. WordPress最新版へ更新（F-009）
14. TLSv1.3対応（F-010）
15. Scrapbox公開設定見直し（EXT-012）
16. ローコードツール利用ポリシー策定

---

## 検証で脆弱でないことを確認した項目

| 項目 | 結果 |
|------|------|
| Clickjacking | 全サイトでX-Frame-Options: SAMEORIGIN設定済 |
| CORS設定不備 | CORSヘッダなし（適切） |
| Host Header Injection | 403で拒否 |
| Cache Poisoning | 脆弱でない |
| DNS Zone Transfer | 拒否 |
| WordPress xmlrpc/REST API | 無効化済 |
| WordPress ユーザー列挙 | 404応答（列挙不可） |
| FTP Anonymous Login | 拒否 |
| セッションID予測 | エントロピー十分 |

---

## 付録: 技術検証資料一覧

各脆弱性の再現手順・技術検証結果を資料として保有しております。
ご要望に応じて提供可能です。

---

## ご連絡のお願い

本報告書に記載した脆弱性については、再現手順の詳細な技術資料を保有しております。ご希望があれば、これらの資料を提供し、脆弱性の再現方法や対策の技術的詳細についてご説明することが可能です。

特にEXT-003（メールスプーフィング）については悪用リスクが極めて高いため、早急なご対応を推奨いたします。

ご不明点やご質問がございましたら、折り返しご連絡いただけますと幸いです。
また、この文章はmd形式で作成されておりmdエディタなどで閲覧することを推奨いたします
---

*本報告書は善意のセキュリティ調査に基づき作成されました。*
*悪用目的は一切ありません。*
*報告書作成日: 2026年4月9日*
