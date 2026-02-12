# RQ1 Evaluation Report (Strict Matching)

- Generated at (UTC): 2026-02-06T10:03:19.328434+00:00
- Dataset: Sherlock Audit Contest Result https://audits.sherlock.xyz/contests/1140?filter=judging (366 issues)
- Filtered issues (union of branches): 11
- Audit item filter: final_classification in [NEEDS-MANUAL-AUDIT, NEEDS-REVIEW, exploitable, vulnerability-confirmed, true-positive, potential-vulnerability, needs-review, requires_review, low-risk-externally-reachable, requires_manual_review, potential_vulnerability_defense_in_depth]
- Issue filter: submitted_severity in [Low, Medium, High] AND issue mentions a CL client

## Experiment Environment
- AI: Claude Code (CLI 2.1.25; Model Claude Code Opus 4.5)

| Branch | Commit | Phase 03 Runtime | Tokens (in/out/total) | Num Turns | Files |
| --- | --- | --- | --- | --- | --- |
| audit_grandine_fusaka-audit_926ec220_20260204173641 | 926ec220 | 10.1m | 69146/225199/29140857 | 143 | 5 |
| audit_lighthouse_fusaka-audit_b8178515c_20260204170145 | b8178515c | 25.8m | 91421/247576/52491144 | 169 | 5 |
| audit_lodestar_fusaka-audit_7931b71e6d_20260204224015 | 7931b71e6d | 19.4m | 366742/838683/114886373 | 257 | 5 |
| audit_nimbus-eth2_fusaka-audit_da9305a98_20260204154410 | da9305a98 | 19.0m | 86869/162729/39663769 | 174 | 5 |
| audit_prysm_fusaka-audit_238d5c07df_20260204173151 | 238d5c07df | 15.3m | 125705/171188/41323551 | 154 | 5 |
| audit_teku_fusaka-audit_35809f4fde_20260204173732 | 35809f4fde | 33.0m | 115476/188845/40327955 | 128 | 5 |

## Matching & Recall

### 判定基準・判定方法

LLM (`gemini-2.5-flash`) を用いて、人間が報告したissueとエージェントが検出したfinding（発見事項）の**直接的な一致 (Strict Match)** を判定しました。

以下の**すべて**を満たす場合にのみマッチと判定します。

1. issueとfindingが**同一の特定のバグ**を記述している。
2. issueとfindingが**同一のコード領域**（関数、ファイル、または密結合したモジュール）を対象としている。
3. issueとfindingが**同一の根本原因**を記述している。

以下の場合はマッチとみなしません。

- findingが同じ一般的な領域（例：「gossip validation」）にあるだけで、異なるバグを指している場合。
- findingが同じバグクラスだが、異なるコードパスを対象としている場合。
- findingが一般的なレビュー推奨であり、たまたまissueの領域をカバーしている場合。
- findingがEIPや機能レベルでのみ一致している場合（例：両方ともEIP-7594に関するが、異なる問題を指している場合）。

### Recallの定義

- `issue_recall = unique_issue_ids_matched / total_issues_in_scope` (ブランチごと)
- 監査範囲内の全issue（Low/Medium/High かつ CLクライアント関連）のうち、エージェントが正しく検出できたものの割合を示します。

### Results Tableの変数定義

| 変数名 | 定義 |
| --- | --- |
| Items | 各ブランチで、指定されたラベル (`NEEDS-MANUAL-AUDIT`, `NEEDS-REVIEW`, `exploitable`, `vulnerability-confirmed`, `true-positive`, `potential-vulnerability`, `needs-review`, `requires_review`, `low-risk-externally-reachable`, `requires_manual_review`, `potential_vulnerability_defense_in_depth`) が付与されたエージェントのfindingの総数。 |
| Matched | `Items`のうち、フィルタされた人間報告issueと厳格な基準で直接的にマッチしたfindingの数。 |
| Overlap | `Matched / Items`。エージェントの発見事項のうち、既知のissueと直接的に重複しているものの割合。 |
| Issues | 各ブランチの監査対象クライアントに関連し、かつ深刻度がLow/Medium/Highである人間報告issueの総数。 |
| Issues Matched | `Issues`のうち、エージェントのfindingと直接的にマッチしたissueの数。 |
| Issue Recall | `Issues Matched / Issues`。監査範囲内のissueをエージェントがどれだけ再現（検出）できたかを示す最重要指標。 |
| New | `Items - Matched`。エージェントが発見したもののうち、既知のissueとはマッチしなかったfindingの数。未知の脆弱性である可能性を示唆する。 |
| LLM Calls | マッチング判定のためにLLMを呼び出した回数。各ブランチの`Issues`の数と一致する。 |

## Results

| Branch | Items | Matched | Overlap | Issues | Issues Matched | Issue Recall | New | LLM Calls |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| audit_grandine_fusaka-audit_926ec220_20260204173641 | 9 | 0 | 0.000 | 2 | 0 | 0.000 | 9 | 2 |
| audit_lighthouse_fusaka-audit_b8178515c_20260204170145 | 54 | 1 | 0.019 | 3 | 1 | 0.333 | 53 | 3 |
| audit_lodestar_fusaka-audit_7931b71e6d_20260204224015 | 5 | 1 | 0.200 | 2 | 1 | 0.500 | 4 | 2 |
| audit_nimbus-eth2_fusaka-audit_da9305a98_20260204154410 | 21 | 0 | 0.000 | 4 | 0 | 0.000 | 21 | 4 |
| audit_prysm_fusaka-audit_238d5c07df_20260204173151 | 114 | 2 | 0.018 | 4 | 2 | 0.500 | 112 | 4 |
| audit_teku_fusaka-audit_35809f4fde_20260204173732 | 51 | 0 | 0.000 | 0 | 0 | 0.000 | 51 | 0 |

- Overall issue recall (Strict, Low/Medium/High, CL clients): **0.273** (3/11)

## マッチしたIssue一覧 (Strict, Low/Medium/High)

| Issue # | Severity | Title | Matched Finding ID | Reason |
| --- | --- | --- | --- | --- |
| #40 | High | Proposer calculation can be incorrect since proposer lookahead is not considered inside get_beacon_proposer_indices | CHECK-W6-PROP-W6-BOUNDARY-MALICIOUS-VALIDATOR-001-NODE | Agent finding directly matches by identifying a cryptographic/proposer calculation boundary issue in the same beacon proposer indices logic. |
| #203 | High | Weak Fiat-Shamir in `c-kzg-4844.verify_cell_kzg_proof_batch` | CHECK-W5-PROP-W7-PCS-VERIFY-INV-001-INTERNAL | Agent finding directly identifies a cryptographic weakness related to Fiat-Shamir challenge determinism and collision resistance in batch verification within the PCS verification context. |
| #381 | Low | Lodestar accepts and rebroadcasts data column sidecars with invalid signatures if column has already been seen | CHECK-W4-PROP-W2-FULU-GOSSIP-PRECOND-05-BOUNDARY | Agent finding directly addresses proposer signature verification for gossip data_column_sidecar and explicitly lists 'Signature Verification Bypass' as the bug class, matching the root cause and code area. |

## マッチしなかったIssue一覧 (Strict, Low/Medium/High)

| Issue # | Severity | Title | Clients | Reason |
| --- | --- | --- | --- | --- |
| #15 | Medium | Nimbus: remote DoS via large custody group count metadata update | status-im/nimbus-eth2 | Agent findings mention input validation / trust boundary violations but none specifically point to the `checkPeerCustody` / `lookupCgcFromPeer` function or the exact unbounded loop vulnerability. |
| #48 | Low | Lighthouse uses latest version 0.9.0 of rust-eth-kzg library which doesn't properly support point of infinity | sigp/lighthouse | None of the agent findings mention the `rust-eth-kzg` library, the point of infinity, or a KZG-related bug that would directly match this description. |
| #109 | Low | Malicious peer will freeze custody rotation for Ethereum beacon nodes | status-im/nimbus-eth2 | Agent findings are too general or refer to different specific pre-conditions/invariants; none specifically point to the `handle_custody_groups` function or the exact unbounded loop. |
| #190 | High | Prysm incorrectly caches the result of `verify_data_column_sidecar_inclusion_proof` | status-im/nimbus-eth2, OffchainLabs/prysm | None of the agent findings directly address a caching issue related to `kzg_commitments` or the `inclusionProofKey` function specifically. |
| #216 | Medium | Nimbus may use stale metadata information after Fulu fork transition | ChainSafe/lodestar, status-im/nimbus-eth2, OffchainLabs/prysm | None of the agent findings directly address stale peer metadata or the `peerPingerHeartbeat` function. |
| #319 | Low | Grandine blob schedule ordering mismatch causes chain split at BPO boundaries | grandinetech/grandine | Agent findings are general checks; none directly address the `blob_schedule` ordering or its impact on chain splits. |
| #343 | Low | No custody peers on partial retry causes indefinite sync stall during BPO rotation | sigp/lighthouse | None of the agent findings directly address `NoPeer` error handling in partial batch retries within the sync mechanism. |
| #376 | Low | Grandine accepts blocks with forged DA due to ignoring KZG verification return value | grandinetech/grandine | Agent findings are high-level checks; none directly address the KZG verification logic or its ignored return value. |

## Raw Metadata
```json
{
  "generated_at": "2026-02-06T10:03:19.328434+00:00",
  "ai": {
    "name": "Claude Code",
    "version": "CLI 2.1.25; Model Claude Code Opus 4.5"
  },
  "notes": {
    "phase_timing_source": "outputs/logs",
    "phase_timing_caveat": "Timing is estimated from phase log timestamps when available."
  }
}
```
