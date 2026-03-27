# Chainlink Payment Abstraction V2 - Final Audit Status
## Date: 2026-03-27 (Contest Deadline: 09:00 JST)

## Submitted Findings (teoshutuzuumi/)
| ID | Severity | Title | Status |
|---|---|---|---|
| H-01 | High | Unrestricted approve() via _multiCall in auctionCallback | Submitted |
| M-01 | Medium | Asymmetric price validation checkUpkeep vs performUpkeep/bid | Submitted |
| M-03 | Medium | Reverting Chainlink data feed blocks ALL auction operations | Submitted |

## Unsubmitted Findings
| ID | Severity | Title | Status |
|---|---|---|---|
| **M-15** | **Medium** | **GPV2 isValidSignature missing minBidUsdValue** | **READY - NOT YET SUBMITTED** |
| M-02 | Low | Shared stalenessThreshold dual oracle | Written, not submitted |
| M-07 | Low | Future timestamp in transmit() | Written, not submitted |
| M-08 | Low | Missing force-clear for stuck auctions | Written, not submitted |
| M-14 | Low | Stale approval after _setAuction | Written, not submitted |

## Friend Versions (outputs/submitted/friend/)
| ID | Title | File |
|---|---|---|
| H-01 | _multiCall selector guard missing | H01_friend_draft.md |
| M-02 | Dual-Oracle Freshness Validation Flaw | M02_dual_oracle_staleness.md |
| M-07 | Missing Upper-Bound Validation on observationsTimestamp | M07_unbounded_observation_timestamp.md |
| M-15 | CowSwap Settlement Path Bypasses Minimum Bid Enforcement | M15_gpv2_missing_min_bid.md |

## Rejected Findings (hinin/)
- C01: Duplicate of H-01
- M04: performUpkeep no validation (AUCTION_WORKER trusted)
- M05: isValidSignature minBid (became M-15 with better writeup)
- M06: bid() slippage (Dutch auction design)

## Total Audit Effort
- 4 rounds CSV pattern matching (44+ patterns, 360MB+)
- 7+ independent fresh audit sessions
- 2 compound attack analyses
- 5 deep code reviews (every contract)
- 1 spec-vs-code gap analysis
- 1 test file reverse engineering
- 2 LLM bulk matching rounds
- 1 scraper refresh (no new data)

## Key Files
- Self M-15: outputs/submitted/M15_submission.md
- Friend M-15: outputs/submitted/friend/M15_gpv2_missing_min_bid.md
- All analysis outputs: outputs/*.md
