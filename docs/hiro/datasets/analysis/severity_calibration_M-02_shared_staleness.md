# Severity Calibration: M-02_shared_staleness

Our finding: Single staleness threshold shared between multiple oracle sources (Data Streams + Chainlink feed fallback). Tight threshold kills fallback, loose threshold accepts stale primary.
Current severity: Low

## Precedent Analysis (30 matches)

Looking at the historical precedents, here's my severity calibration analysis:

## Top 5 Most Relevant Precedents

1. **Tapioca (2023-07) - Medium #1505** - Nearly identical issue: "Using the same heartbeat for all Chainlink feeds will either result in frequent reverts or stale prices." This is exactly our shared staleness threshold problem.

2. **Paraspace (2022-11) - Medium #420/#419** - Fallback oracle not used during outages/disagreements. Similar impact where poor configuration prevents fallback mechanism from working.

3. **Salty (2024-01) - Medium #501** - Inappropriate staleness threshold (60min too short) allowing price manipulation. Shows staleness threshold configuration issues rated Medium.

4. **Juicebox (2022-07) - High #150/#85/#58** - Multiple High findings for stale oracle data, but these involve completely missing staleness checks rather than shared misconfiguration.

5. **Badger (2023-10) - High #238** - Missing oracle status validation making prices vulnerable, but again involves missing checks entirely.

## Key Differences in Trust Model

The precedents don't clearly indicate trust models, but our finding appears to be in a system where:
- **Our case**: Likely has admin/governance capability to adjust parameters (mitigating factor)
- **Precedents**: Most appear to be hardcoded or difficult-to-change configurations

## Severity Calibration Assessment

**Current "Low" severity appears too conservative.** Here's why:

- **Most similar precedent (Tapioca #1505)**: Identical technical issue, rated **Medium**
- **Pattern across precedents**: Staleness threshold configuration issues consistently rated **Medium**
- **Impact potential**: Real risk of either killing fallback or accepting stale primary data
- **Common severity**: Medium for configuration issues, High for missing checks entirely

## Recommendation: Upgrade to **Medium**

The finding matches established Medium-severity precedents for oracle staleness threshold configuration issues. While it may be parameterizable (reducing severity), the core technical risk and precedent alignment supports Medium severity.