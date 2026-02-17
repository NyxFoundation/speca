#!/usr/bin/env python3
"""
Detect target repository layer (consensus/execution) by analyzing codebase structure.

Usage:
    python3 scripts/detect_target_layer.py --target-repo OffchainLabs/prysm
"""

import argparse
import re
from pathlib import Path
from typing import Literal


LAYER_INDICATORS = {
    "consensus": [
        # Directory patterns
        r"beacon[-_]chain",
        r"validator",
        r"attestation",
        r"slashing",
        r"forkchoice",
        r"consensus",
        # File patterns
        r"beacon.*\.go$",
        r"validator.*\.go$",
        r"attestation.*\.go$",
        # Go import patterns (would need code analysis)
        r"github\.com/prysmaticlabs/prysm",
    ],
    "execution": [
        # Directory patterns
        r"core/state",
        r"core/vm",
        r"core/types",
        r"eth/downloader",
        r"miner",
        r"txpool",
        # File patterns
        r"state_transition.*\.go$",
        r"evm.*\.go$",
        r"transaction.*\.go$",
        # Go import patterns
        r"github\.com/ethereum/go-ethereum",
    ],
}


def detect_layer_from_repo_name(repo_name: str) -> Literal["consensus", "execution", "unknown"]:
    """
    Quick detection based on repository name.

    Known repos:
        Consensus: prysm, lighthouse, teku, nimbus, lodestar
        Execution: geth, go-ethereum, nethermind, besu, erigon, reth
    """
    repo_lower = repo_name.lower()

    consensus_repos = {"prysm", "lighthouse", "teku", "nimbus", "lodestar"}
    execution_repos = {"geth", "go-ethereum", "nethermind", "besu", "erigon", "reth"}

    for name in consensus_repos:
        if name in repo_lower:
            return "consensus"

    for name in execution_repos:
        if name in repo_lower:
            return "execution"

    return "unknown"


def detect_layer_from_directory_structure(workspace_path: Path) -> Literal["consensus", "execution", "unknown"]:
    """
    Detect layer by analyzing directory structure.

    Args:
        workspace_path: Path to target repository workspace

    Returns:
        Detected layer: "consensus", "execution", or "unknown"
    """
    if not workspace_path.exists():
        return "unknown"

    consensus_score = 0
    execution_score = 0

    # Walk through directories
    for item in workspace_path.rglob("*"):
        if not item.is_dir() and not item.is_file():
            continue

        relative_path = str(item.relative_to(workspace_path))

        # Check consensus indicators
        for pattern in LAYER_INDICATORS["consensus"]:
            if re.search(pattern, relative_path, re.IGNORECASE):
                consensus_score += 1

        # Check execution indicators
        for pattern in LAYER_INDICATORS["execution"]:
            if re.search(pattern, relative_path, re.IGNORECASE):
                execution_score += 1

    # Decision based on scores
    if consensus_score > execution_score * 2:
        return "consensus"
    elif execution_score > consensus_score * 2:
        return "execution"
    else:
        return "unknown"


def detect_target_layer(target_repo: str, workspace_path: Path | None = None) -> Literal["consensus", "execution", "unknown"]:
    """
    Detect target repository layer using multiple heuristics.

    Args:
        target_repo: Repository identifier (e.g., "OffchainLabs/prysm")
        workspace_path: Optional path to target workspace for directory analysis

    Returns:
        Detected layer: "consensus", "execution", or "unknown"
    """
    # Try repo name first (fastest)
    layer = detect_layer_from_repo_name(target_repo)
    if layer != "unknown":
        return layer

    # Try directory structure analysis if workspace provided
    if workspace_path:
        layer = detect_layer_from_directory_structure(workspace_path)
        if layer != "unknown":
            return layer

    return "unknown"


def main():
    parser = argparse.ArgumentParser(description="Detect target repository layer")
    parser.add_argument(
        "--target-repo",
        required=True,
        help="Target repository (e.g., OffchainLabs/prysm)",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        help="Optional path to target workspace for directory analysis",
    )

    args = parser.parse_args()

    layer = detect_target_layer(args.target_repo, args.workspace)

    print(f"Target Repository: {args.target_repo}")
    print(f"Detected Layer: {layer}")

    if layer == "unknown":
        print("\nWarning: Could not confidently detect target layer.")
        print("Recommendation: Manually specify target layer or provide workspace path.")


if __name__ == "__main__":
    main()
