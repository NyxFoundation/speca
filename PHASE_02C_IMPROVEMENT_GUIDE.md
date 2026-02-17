# Phase 02c Improvement Guide

## 問題の概要

Phase 02c（コードマッピング）で大量の`not_found`が発生した根本原因：

1. **仕様とターゲットの不一致** (最重要)
   - 実行レイヤー(EL)の仕様を、コンセンサスレイヤー(CL)の`prysm`に対してマッピング
   - 18個のEL仕様が存在し、これらはCLコードベースに存在しない

2. **エージェントの意図的な処理制限**
   - 完全なコールグラフ分析には500-1000 MCP呼び出しが必要
   - コスト/時間制約により簡易的なキーワード検索のみ実行
   - 未マッチを積極的に`not_found`として処理

3. **MCP Tree-sitterの散発的エラー**
   - `'tree_sitter.Query' object has no attribute 'captures'`
   - 約10回発生、副次的な影響

## 解決策の概要

6つの統合的な改善を提案します：

1. **レイヤーフィルタリング機構** - Phase 01a/01b段階でのフィルタリング
2. **ターゲット検証機構** - Phase 02c開始前の適合性検証
3. **レイヤー不一致の明示的処理** - `layer_mismatch`ステータスの導入
4. **MCPエラーハンドリング強化** - リトライとフォールバック戦略
5. **予算・タイムアウト調整** - 完全なコールグラフ分析を可能に
6. **Phase 03の最適化** - 事前解決されたコード情報の活用

## 実装手順

### Step 1: 新規スクリプトの追加

以下のスクリプトが`scripts/`ディレクトリに追加されました：

```bash
scripts/
├── filter_specs_by_layer.py          # 仕様をレイヤーでフィルタリング
├── detect_target_layer.py            # ターゲットレイヤーの自動検出
└── enrich_checklist_with_layer_info.py  # チェックリストに層情報を追加
```

**実行可能にする：**

```bash
chmod +x scripts/filter_specs_by_layer.py
chmod +x scripts/detect_target_layer.py
chmod +x scripts/enrich_checklist_with_layer_info.py
```

**テスト実行：**

```bash
# ターゲットレイヤーの検出
python3 scripts/detect_target_layer.py --target-repo "OffchainLabs/prysm"
# Expected output: Detected Layer: consensus

# 仕様のフィルタリング（テスト）
python3 scripts/filter_specs_by_layer.py \
    --input outputs/01a_STATE.json \
    --output outputs/01a_STATE_FILTERED_CL.json \
    --target-layer consensus
```

### Step 2: パッチの適用

3つのパッチファイルが`patches/`ディレクトリに作成されました：

```bash
patches/
├── 02c_layer_mismatch_detection.patch  # レイヤー不一致検出ロジック
├── 02c_mcp_error_handling.patch        # MCPエラーハンドリング
└── 02c_budget_adjustment.patch         # 予算・タイムアウト調整
```

**適用方法：**

```bash
# 1. レイヤー不一致検出を有効化
git apply patches/02c_layer_mismatch_detection.patch

# 2. MCPエラーハンドリングを強化
git apply patches/02c_mcp_error_handling.patch

# 3. 予算とタイムアウトを調整
git apply patches/02c_budget_adjustment.patch
```

**パッチ適用の確認：**

```bash
# 変更されたファイルを確認
git status

# 変更内容を確認
git diff prompts/02c_codelocation_worker.md
git diff scripts/orchestrator/config.py
```

### Step 3: 監査ワークフローの更新

#### オプションA: 事前フィルタリング（推奨）

Phase 01aの直後に仕様をフィルタリング：

```bash
# 1. Phase 01a実行（通常通り）
uv run python3 scripts/run_phase.py --phase 01a

# 2. ターゲットレイヤーの検出
TARGET_LAYER=$(python3 scripts/detect_target_layer.py \
    --target-repo "OffchainLabs/prysm" \
    --workspace "target_workspace" | grep "Detected Layer:" | awk '{print $3}')

# 3. 仕様をフィルタリング
python3 scripts/filter_specs_by_layer.py \
    --input outputs/01a_STATE.json \
    --output outputs/01a_STATE_FILTERED.json \
    --target-layer ${TARGET_LAYER}

# 4. フィルタリングされた仕様でPhase 01bを実行
# (01a_STATE_FILTERED.jsonを01a_STATE.jsonとして使用)
mv outputs/01a_STATE.json outputs/01a_STATE_ORIGINAL.json
mv outputs/01a_STATE_FILTERED.json outputs/01a_STATE.json

# 5. 残りのPhaseを実行
uv run python3 scripts/run_phase.py --target 04 --workers 4
```

#### オプションB: Phase 02c内での動的フィルタリング

パッチ適用後、Phase 02cが自動的にレイヤー不一致を検出：

```bash
# Phase 02cがレイヤー不一致を検出し、`layer_mismatch`としてマーク
uv run python3 scripts/run_phase.py --phase 02c --workers 4

# 結果の確認
jq '.checklist_with_code[] | select(.code_scope.resolution_status == "layer_mismatch") | {check_id, status: .code_scope.resolution_status, error: .code_scope.resolution_error}' \
    outputs/02c_PARTIAL_W0B1_*.json | head -20
```

### Step 4: Phase 02cの再実行（現在の監査に対して）

既存の監査（`preresolve_prysm_fusaka-audit_238d5c07df_20260216163454`ブランチ）を修正：

```bash
# 1. ブランチをチェックアウト
git checkout preresolve_prysm_fusaka-audit_238d5c07df_20260216163454

# 2. masterから最新の変更をマージ（パッチ適用後）
git merge master -m "feat: apply Phase 02c improvements for layer mismatch detection"

# 3. 仕様をコンセンサスレイヤーでフィルタリング
python3 scripts/filter_specs_by_layer.py \
    --input outputs/01a_STATE.json \
    --output outputs/01a_STATE_FILTERED.json \
    --target-layer consensus

# バックアップと置き換え
mv outputs/01a_STATE.json outputs/01a_STATE_ORIGINAL.json
cp outputs/01a_STATE_FILTERED.json outputs/01a_STATE.json

# 4. Phase 02とPhase 02cを再実行
uv run python3 scripts/run_phase.py --phase 02 --force --workers 4
uv run python3 scripts/run_phase.py --phase 02c --force --workers 8 --max-concurrent 32

# 5. 結果の比較
python3 scripts/compare_02c_results.py \
    --before outputs/02c_PARTIAL_*_BEFORE.json \
    --after outputs/02c_PARTIAL_*.json
```

### Step 5: 結果の検証

#### 予想される改善

**Before（現状）:**
- Resolved: 520/1304 (39.9%)
- Not Found: 584/1304 (44.8%)
- Errors: 200/1304 (15.3%)

**After（改善後）:**
- Resolved: 700+/1304 (53%+) - レイヤー適合仕様のマッピング率向上
- Layer Mismatch: 400+/1304 (30%+) - EL仕様を明示的に分離
- Not Found: 150/1304 (11%) - レイヤー適合仕様内での未発見
- MCP Error: 30/1304 (2%) - リトライ後のMCPエラー
- Errors: 24/1304 (2%) - その他エラー

**検証コマンド:**

```bash
# ステータス別の集計
jq -r '.checklist_with_code[] | .code_scope.resolution_status' outputs/02c_PARTIAL_*.json | sort | uniq -c

# レイヤー不一致の詳細
jq '.checklist_with_code[] | select(.code_scope.resolution_status == "layer_mismatch") | {check_id, error: .code_scope.resolution_error}' \
    outputs/02c_PARTIAL_*.json | jq -s 'group_by(.error) | map({error: .[0].error, count: length})'

# 解決率の比較（レイヤー適合仕様のみ）
echo "Resolution rate (layer-matched specs only):"
jq -r '.checklist_with_code[] | select(.code_scope.resolution_status != "layer_mismatch") | .code_scope.resolution_status' \
    outputs/02c_PARTIAL_*.json | grep -c "resolved"
```

## コスト・パフォーマンス分析

### Phase 02c予算の変更

- **Before:** $10.00
- **After:** $25.00 (+150%)
- **理由:** 完全なコールグラフ分析を可能に

### Phase 03予算の削減効果

- **Phase 03の予想削減:** $12-18 (40-60%のトークン削減)
- **理由:** Phase 02cで事前解決されたコード情報を利用

### 総コスト影響

- **Phase 02c増加:** +$15
- **Phase 03削減:** -$12 to -$18
- **ネット影響:** -$3 to +$3 (実質的にニュートラル)

**追加効果:**
- Phase 03の実行時間が30-40%短縮
- より正確なコードマッピング（Phase 03の監査精度向上）
- レイヤー不一致の明示化（報告品質向上）

## トラブルシューティング

### パッチ適用エラー

```bash
# パッチが適用できない場合（コンフリクト）
git apply --reject patches/02c_layer_mismatch_detection.patch
# → *.rejファイルを確認し、手動でマージ
```

### MCPエラーが継続する場合

```bash
# Tree-sitter MCPサーバーを再起動
bash scripts/setup_mcp.sh --verify

# キャッシュをクリア
rm -rf ~/.cache/tree-sitter/
```

### レイヤー検出が不正確な場合

```bash
# 手動でレイヤーを指定
TARGET_LAYER="consensus"  # または "execution"
python3 scripts/filter_specs_by_layer.py \
    --input outputs/01a_STATE.json \
    --output outputs/01a_STATE_FILTERED.json \
    --target-layer ${TARGET_LAYER}
```

## 今後の改善案

### Phase 02cの更なる最適化

1. **キャッシュ機構の導入**
   - エントリーポイントのコールグラフをディスクにキャッシュ
   - 複数バッチ/ワーカー間で共有

2. **並列MCP呼び出し**
   - 独立したMCP呼び出しを並列実行
   - asyncioベースの実装

3. **段階的コールグラフ構築**
   - 深さ1で開始 → マッチ確認 → 必要に応じて深さ2-3へ拡張
   - 不要な深い探索を回避

### Phase 01aの改善

1. **仕様メタデータの拡張**
   - `applicable_clients`フィールドを追加
   - 例: `"applicable_clients": ["prysm", "lighthouse", "teku"]`

2. **スコープ情報の追加**
   - `affects_consensus`, `affects_execution`, `affects_networking`
   - より細かいフィルタリングを可能に

### Phase 03の最適化

1. **事前解決情報の活用**
   - Phase 02cの`code_scope.locations`を直接利用
   - 冗長なMCP呼び出しを削減

2. **レイヤー不一致のスキップ**
   - `layer_mismatch`アイテムをPhase 03でスキップ
   - Phase 04で別カテゴリとして報告

## まとめ

このガイドに従うことで、以下の改善が期待されます：

1. **コードマッピング精度の向上**: 53%+ (現状39.9%)
2. **レイヤー不一致の明示化**: 30%+のアイテムを`layer_mismatch`として識別
3. **Phase 03のトークン削減**: 40-60%削減
4. **総コストの最適化**: 実質的にニュートラル（Phase 02c増加 ≈ Phase 03削減）
5. **監査品質の向上**: より正確なコードマッピングによる監査精度の向上

## 参考資料

- Phase 02c Worker Prompt: `prompts/02c_codelocation_worker.md`
- Orchestrator Config: `scripts/orchestrator/config.py`
- Tree-sitter MCP: `scripts/setup_mcp.sh`
- コードマッピング失敗分析レポート: (ユーザー提供)

## 変更履歴

- 2026-02-17: 初版作成（Phase 02c改善ガイド）
