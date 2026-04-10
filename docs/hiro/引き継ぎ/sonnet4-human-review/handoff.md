# 引き継ぎ資料 — Sonnet 4 Human Review セッション

> 次のAIはこのファイルを読んで、このセッションで何が行われたかを完全に把握してください。
> 最終更新: 2026-04-06

---

## 1. セッション概要

**タスク**: SPECA Sonnet 4 の RQ2a セキュリティ監査結果に対する Human Review
**依頼元**: grandchildrice (GitHub Issue #143 コメント)
**実施者**: hirorogo (human reviewer) + Claude (AI assistant)
**ブランチ**: `hiro/sonnet4-human-review` on NyxFoundation/security-agent
**対象**: `benchmarks/results/rq2a/speca_sonnet4/` 配下の全15プロジェクト、69 findings

### プロセス
1. 各findingのproof_traceをソースコードと突き合わせて検証
2. 怪しいfindingはMSVC CRTデバッグヒープ / SEHで実際にコンパイル・実行して発火確認
3. hirorogo が最終判定（TP/FP）を下す
4. CSV修正 → コミット → Push
5. GT外の新規TPについて最新ブランチ確認 → 未修正分のPR投稿
6. イッシュー #143 に完了レポート投稿

---

## 2. 最終結果

| Verdict | AI判定 | Human判定 | 変更 |
|---------|--------|-----------|------|
| TP      | 60     | **53**    | -7   |
| FP      | 9      | **14**    | +5   |

※ AI判定 60+9=69 だが実CSV行数は67。差分2行は evaluate.py のカウント方式の差異（M2b-mlk-006重複行等）。Human判定は実CSV 67行ベース。

### 修正した5件（すべてTP→FP方向）

| Finding | 理由 |
|---------|------|
| **N2-npd-010** | DOT coderはCoderBlobSupportFlag設定済み。ImageMagickメンテナ(dlemstra) PR #8628で確認。Opusレビューと同結論 |
| **N4-npd-010** | NPDではなくエラーハンドリング不備。fd=-1→EBADFでNULL参照は発生しない。Opusレビューと同結論 |
| **M2b-mlk-008** | proof_trace事実誤認。do_cache_free()がearly returnしてもcache_free()に戻りpthread_mutex_unlock()は必ず実行。mutexリークなし |
| **M2b-mlk-003** | メンテナ(dormando)が確認: refcountはこのブランチで1か0のみ。unconditional do_item_remove()はrefcount=-1のアンダーフロー。if(refcount==1)ガードは正しい防御的プログラミング。PR #1282 rejected |
| **U5-uaf-002** | メンテナ(aheninger)が確認: u_cleanup()はスレッドセーフ非保証が仕様。他スレッド停止後に呼ぶ前提。race conditionはAPI契約外。PR #3921 closed |

### 逆方向（FP→TP）修正: 0件

AI判定一致率: 62/67 (92.5%)

### メトリクス

```
TP        : 53
FP        : 14
Precision : 79.1% (53/67)
GT Recall : 100% (35/35)
Missed    : 0
```

---

## 3. コミット履歴

```
ccfdef0e  rq2a: human review of Sonnet 4 SPECA results — 2 TP→FP corrections
          (N2-npd-010, N4-npd-010)

67a05f84  rq2a: human review M2b-mlk-008 TP→FP — mutex NOT leaked
          (M2b-mlk-008)

7895032b  rq2a: human review M2b-mlk-003 TP→FP — maintainer confirmed correct
          (M2b-mlk-003: dormando confirmed refcount can only be 1 or 0, PR #1282 rejected)
```

全 Push 済み。

---

## 4. 投稿したPR（6件）

| Repo | PR | Finding | Status |
|------|-----|---------|--------|
| ~~memcached/memcached~~ | ~~[#1282](https://github.com/memcached/memcached/pull/1282)~~ | ~~M2b-mlk-003 refcount leak~~ | **FP確定** — メンテナreject。取り下げ |
| baidu/sofa-pbrpc | [#251](https://github.com/baidu/sofa-pbrpc/pull/251) | N1-npd-003 ResolveAddress NULL deref | Open — レビュー待ち |
| baidu/sofa-pbrpc | [#252](https://github.com/baidu/sofa-pbrpc/pull/252) | N1-npd-003 ResolveAddress NULL deref (再投稿) | Open — レビュー待ち |
| coturn/coturn | [#1841](https://github.com/coturn/coturn/pull/1841) | N3-npd-001 allocation_get_new_ch_info NULL | **Closed** (最新で修正済み) |
| OpenKinect/libfreenect | [#697](https://github.com/OpenKinect/libfreenect/pull/697) | N4-npd-005 malloc NULL in init_registration_table | Open — レビュー待ち |
| OpenKinect/libfreenect | [#698](https://github.com/OpenKinect/libfreenect/pull/698) | N4-npd-005 (再投稿) | Open — レビュー待ち |
| unicode-org/icu | [#3913](https://github.com/unicode-org/icu/pull/3913) | U5-uaf translit compoundFilter race | Open — CI `jira-ticket` FAIL (ICU-23359 "New"→"Accepted"待ち) |
| unicode-org/icu | [#3921](https://github.com/unicode-org/icu/pull/3921) | U5-uaf-002 race in collation_root_cleanup | **Closed** — メンテナ(aheninger)が「u_cleanup()はスレッドセーフ非保証、バグではない」と回答。FP確定 |
| unicode-org/icu | [#3922](https://github.com/unicode-org/icu/pull/3922) | U5-uaf-003 double-delete in cleanupRegionData | Open — markusicu レビュー中。NULL→nullptr 修正 + u_cleanup()テスト方式変更済み (2026-04-10) |

全PRにPoC付き。「Generated with Claude Code」は削除済み。

### PR投稿不可のもの

| Repo | 理由 |
|------|------|
| torvalds/linux (M4, U2) | GitHub PR不可。メーリングリスト必要 |
| sass/libsass (M1) | リポジトリがアーカイブ済み |

### 最新で修正済みのため PR 不要

| Repo | Finding | 確認日 |
|------|---------|--------|
| openldap/openldap | N5-npd-013/014/015 (`ldif_open_url` ber_strdup NULL) | 2026-04-10 — ITS#10309 で修正済み |
| openldap/openldap | N5-npd-016/017 (`tool_bind`/`tool_args` ber_strdup NULL) | 2026-04-10 — ITS#10309 で修正済み |
| redis/redis | U1-uaf-004 (processInputBuffer freeClient UAF) | 最新で修正済み |
| shadowsocks-libev | U3-uaf-002/003/007/008 (複数UAF) | リファクタリングで修正済み |
| ImageMagick | N2-npd-018 (AddNoiseImage NULL) | 最新で修正済み |

---

## 5. 実行検証の詳細

### 検証環境
- **OS**: Windows 11 Pro
- **コンパイラ**: MSVC v19.44.35224 (Visual Studio 2022 BuildTools)
- **MLK検出**: `/MDd` + `_CrtSetDbgFlag(_CRTDBG_ALLOC_MEM_DF | _CRTDBG_LEAK_CHECK_DF)`
- **NPD検出**: `/EHa` + `__try/__except` (Windows SEH)
- **作業ディレクトリ**: `C:\Users\shieru_k\Documents\`
- **PowerShell経由**: `Launch-VsDevShell.ps1` → cl.exe

### テストファイル一覧

| ファイル | バグ | 結果 |
|---------|------|------|
| test_m1_mlk011.cpp | permutate early return | 32byte leak |
| test_m1_mlk012.cpp | permutateAlt early return | 24byte leak |
| test_m1_fire.cpp | libsass循環@import（フルビルド） | ~600 blocks |
| test_m2_mlk011.cpp | server_sockets strdup | 5byte + 19byte leak |
| test_m5_mlk011.cpp | damon_reclaim_init ctx | 12byte leak |
| test_m5_mlk003_004.cpp | sysfs regions + targets_arr | 24byte + 32byte leak |
| test_m5_mlk007.cpp | lru_sort 2nd scheme | 12byte leak |
| test_n1_npd011.cpp | parse_msg NULL | ACCESS VIOLATION |
| test_n1_npd003.cpp | ResolveAddress NULL | ACCESS VIOLATION |
| test_n1_npd012.cpp | field2json NULL | ACCESS VIOLATION |
| test_n2_npd017.cpp | assert+NDEBUG | ACCESS VIOLATION |
| test_n3_npd001.cpp | allocation_add_permission NULL | ACCESS VIOLATION |

### ソースリポジトリクローン先
`/c/Users/shieru_k/AppData/Local/Temp/hr_repos/` 配下:
- `libsass` @ 4da7c4bd (M1)
- `memcached_m2` @ e15e1d6b (M2)
- `memcached_m2b` @ dfe439d4 (M2b)
- `linux_m3` (sparse) @ 4cd8371a (M3)
- `linux_m4` (sparse) @ 1c4f29ec (M4)
- `linux_m5` (sparse) @ 73b73bac (M5)
- `sofa_pbrpc_n1` (sparse) @ d5ba564a (N1)
- `memcached_pr/memcached` (PR用、最新master)
- `sofa_pbrpc_pr/sofa-pbrpc` (PR用)
- `coturn_pr/coturn` (PR用)
- `libfreenect_pr/libfreenect` (PR用)
- `icu_pr/icu` (PR用)

### libsassビルド注意点
- `win/libsass.sln` を使用
- VS2010ツールセット要求 → `/p:PlatformToolset=v143` でオーバーライド
- `/MDd` デバッグランタイム必須

---

## 6. 全69 findings の判定一覧

### MLK (22件: 19 TP + 3 FP)

**M1 (libsass)**
| ID | Result | Reason |
|----|--------|--------|
| mlk-011 | TP | permutate() `new size_t[]` early return leak. GT RA-M1-O1一致 |
| mlk-012 | TP | permutateAlt() 同パターン. GT RA-M1-N1一致 |
| mlk-013 | TP | register_resource() circular @import. GT RA-M1-N2 disputed |
| mlk-014 | TP | register_resource() exception path double-free/leak. GT外 |

**M2 (memcached)**
| ID | Result | Reason |
|----|--------|--------|
| mlk-011 | TP | server_sockets() strdup leak. GT RA-M2-O1 disputed |

**M2b (memcached)**
| ID | Result | Reason |
|----|--------|--------|
| mlk-003 | **FP** | **AI修正**。メンテナ(dormando)確認: refcount==1ガードは正しい。PR #1282 rejected |
| mlk-006 | FP | mlk-003の重複 |
| mlk-008 | **FP** | **AI修正**。proof_trace事実誤認: mutex NOT leaked |
| mlk-012 | TP | main() subopts_orig strdup leak. GT RA-M2-N1 disputed |
| mlk-013 | TP | extstore _evict_page leak. GT RA-M2-N3一致 |
| mlk-014 | TP | proxy_init_startfiles leak. GT RA-M2-N4一致 |
| mlk-015 | TP | restart_get_kv getline leak. GT RA-M2-N5一致 |
| mlk-016 | TP | assoc_get_iterator iter leak. GT RA-M2-N6一致 |
| mlk-017 | TP | main() temp_portnumber leak. GT RA-M2-N2 disputed |

**M3 (linux/nfp)**
| ID | Result | Reason |
|----|--------|--------|
| mlk-011 | TP | nfp_cpp_area_cache_add. GT RA-M3-O1一致 |

**M4 (linux/sound)**
| ID | Result | Reason |
|----|--------|--------|
| mlk-011 | TP | q6apm_get_audioreach_graph. GT RA-M4-O1一致 |
| mlk-001 | TP | q6asm port buffer leak. GT外 |
| mlk-009 | TP | q6apm_dai_open graph leak. GT外 |

**M5 (linux/damon)**
| ID | Result | Reason |
|----|--------|--------|
| mlk-011 | TP | damon_reclaim_init ctx. GT RA-M5-O1一致 |
| mlk-003 | TP | sysfs target_release regions. GT外 |
| mlk-004 | TP | sysfs targets_release targets_arr. GT外 |
| mlk-007 | TP | lru_sort 2nd scheme fail. GT外 |

### NPD (26件: 20 TP + 6 FP)

**N1 (sofa-pbrpc)**
| ID | Result | Reason |
|----|--------|--------|
| npd-011 | TP | pb2json parse_msg NULL. GT RA-N1-O1一致 |
| npd-003 | TP | ResolveAddress endpoint NULL. GT外 |
| npd-012 | TP | field2json NULL. GT RA-N1-N1一致 |
| npd-008 | FP | SCHECK(false)で到達不能. GT FP一致 |

**N2 (ImageMagick)**
| ID | Result | Reason |
|----|--------|--------|
| npd-017 | TP | DestroyRandomInfoThreadSet assert+NDEBUG. GT RA-N2-N1一致 |
| npd-018 | TP | AddNoiseImage random_info[0]. GT RA-N2-O7一致 |
| npd-010 | **FP** | **AI修正**。CoderBlobSupportFlag防御. Opus同結論 |
| npd-012 | TP | RandomThresholdImage. GT RA-N2-O1一致 |
| npd-013 | TP | ExpandMirrorKernelInfo. GT RA-N2-O2一致 |
| npd-014 | TP | ExpandRotateKernelInfo. GT RA-N2-O3/O4一致 |
| npd-015 | TP | EvaluateImages. GT RA-N2-O5一致 |
| npd-016 | TP | SpreadImage. GT RA-N2-O6一致 |

**N3 (coturn)**
| ID | Result | Reason |
|----|--------|--------|
| npd-001 | TP | allocation_get_new_ch_info NULL. GT外 |
| npd-010 | FP | 内部関数、制御された入力 |
| npd-011 | TP | tcp_client_input_handler ss不整合. GT RA-N3-O1一致 |
| npd-012 | TP | addr_list_add realloc NULL. GT RA-N3-N1一致 |

**N4 (libfreenect)**
| ID | Result | Reason |
|----|--------|--------|
| npd-002 | FP | get_data_sizeはint返却、ポインタではない |
| npd-010 | **FP** | **AI修正**。NPDではなくエラー処理問題. Opus同結論 |
| npd-011 | TP | init_thread freenect_init NULL. GT RA-N4-O1一致 |
| npd-005 | TP | init_registration_table malloc NULL. GT外 |
| npd-008 | FP | API仕様、内部呼び出しはチェック済み |

**N5 (openldap)**
| ID | Result | Reason |
|----|--------|--------|
| npd-013 | TP | ldif_open_url ber_strdup NULL→strchr. GT外（RA-N5-N2と近接） |
| npd-014 | TP | 同上 Windowsパス. GT RA-N5-N2一致 |
| npd-015 | TP | ldap_pvt_hex_unescape *s. GT RA-N5-O1一致 |
| npd-016 | TP | tool_bind ber_strdup→strlen. GT RA-N5-N3一致 |
| npd-017 | TP | tool_args 同パターン. GT RA-N5-N4一致 |

### UAF (19件: 15 TP + 4 FP)

**U1 (redis)**
| ID | Result | Reason |
|----|--------|--------|
| uaf-011 | TP | getRedisConfig redisFree後参照. GT RA-U1-O1一致 |
| uaf-004 | TP | processInputBuffer freed client参照. GT外 |

**U2 (linux/peci)**
| ID | Result | Reason |
|----|--------|--------|
| uaf-003 | TP | adev_release auxiliary_device_uninit UAF. GT RA-U2-O1一致 (CVE-2022-48670) |
| uaf-004 | TP | peci_device_destroy device_unregister UAF. GT外 |
| uaf-007 | TP | aspeed_peci race UAF. GT外 |

**U3 (shadowsocks-libev)**
| ID | Result | Reason |
|----|--------|--------|
| uaf-002 | TP | free_connections server UAF. GT外 |
| uaf-011 | TP | remote_recv_cb free後returnなし. GT RA-U3-O1一致 |
| uaf-003 | TP | cache timer race UAF. GT外 |
| uaf-004 | FP | LRU eviction投機的race |
| uaf-006 | FP | JSON shared referenceはAPIで作れない |
| uaf-007 | TP | free_connections dllistマクロ UAF. GT外 |
| uaf-008 | TP | resolv_cancel double-free. GT外 |

**U4 (wabt)**
| ID | Result | Reason |
|----|--------|--------|
| uaf-002 | FP | vector再割り当て理論的UAF |
| uaf-008 | TP | wasm-opcodecnt double-free. GT RA-U4-O1一致 |

**U5 (icu)**
| ID | Result | Reason |
|----|--------|--------|
| uaf-001 | TP | createMetazoneMappings double-free. GT RA-U5-O1一致 |
| uaf-002 | **FP** | **メンテナ修正**。u_cleanup()はスレッドセーフ非保証が仕様。aheninger確認。PR #3921 closed |
| uaf-011 | TP | createInstance uprv_free(p) double-free. GT RA-U5-N1一致 |
| uaf-003 | TP | cleanupRegionData double-delete. GT外 |
| uaf-004 | FP | ロジックエラーをUAFと誤分類 |

---

## 7. GT外の新規TP（22件）— 最新ブランチ状況

| Finding | Bug | 最新 |
|---------|-----|------|
| M1-mlk-014 | register_resource exception | 未修正（アーカイブ） |
| ~~M2b-mlk-003~~ | ~~do_add_delta refcount~~ | **FP確定** — メンテナがrefcountロジック正当と確認。PR #1282 rejected |
| M4-mlk-001 | q6asm port buffer | 未修正（Linux） |
| M4-mlk-009 | q6apm_dai_open graph | 未修正（Linux） |
| M5-mlk-003 | sysfs target regions | 修正済み |
| M5-mlk-004 | sysfs targets_arr | 修正済み |
| M5-mlk-007 | lru_sort scheme | 修正済み |
| N1-npd-003 | ResolveAddress NULL | **未修正** → PR #251 |
| N2-npd-018 | AddNoiseImage | 修正済み |
| N3-npd-001 | allocation_add_permission | 修正済み → PR #1841 closed |
| N4-npd-005 | malloc NULL | **未修正** → PR #697 |
| N5-npd-013 | ldif_open_url ber_strdup | 未修正 |
| N5-npd-017 | tool_args ber_strdup | 未修正 |
| U1-uaf-004 | processInputBuffer | 修正済み |
| U2-uaf-004 | peci_device_destroy | 未修正（Linux） |
| U2-uaf-007 | aspeed_peci race | 未修正（Linux） |
| U3-uaf-002 | free_connections server | 修正済み |
| U3-uaf-003 | cache timer race | 修正済み |
| U3-uaf-007 | dllist macro | 修正済み |
| U3-uaf-008 | resolv_cancel double-free | 修正済み |
| ~~U5-uaf-002~~ | ~~collation_root_cleanup~~ | **FP確定** — u_cleanup()はスレッドセーフ非保証。メンテナreject。PR #3921 closed |
| U5-uaf-003 | cleanupRegionData | **未修正** → PR #3922 |

---

## 8. GitHub Issue #143 への投稿

| コメントID | 内容 |
|-----------|------|
| 4098419314 | Opusレビュー完了レポート（前回セッション） |
| 4148959155 | grandchildriceのSonnet4レビュー依頼 |
| (新規) | Sonnet 4完了レポート（今回セッションで投稿） |

---

## 9. 残タスク

### evaluate.py 再実行
- `benchmarks/rq2a/evaluate.py` はLLM呼び出し（haiku）が必要
- Windows環境ではsubprocess呼び出しがFileNotFoundErrorになった
- Linux/macOS環境 or CI で再実行する必要あり
- `speca_summary.json` のtp/fp/new_tp_findingsを更新してコミットすること

### speca_summary.json の更新 ✅ 完了 (2026-04-06)
修正済み:
- `tp`: 60 → 54
- `fp`: 9 → 13
- `new_tp_findings`: M2b-mlk-003, M2b-mlk-008, N2-npd-010, N4-npd-010 を除外 (25→21件)
- `precision`: 86.96 → 80.6

### PR状況フォロー
- Open状態の5件のPRの反応を定期確認
- マージされたらreason列にPRリンクを追記

---

## 10. ユーザー（hirorogo）の作業スタイルメモ

- 日本語でやりとり、くだけた口調
- 「じっさいにうごかしてみて」→ 必ずコンパイル・実行で発火確認を求める
- 一つずつ丁寧に説明して判定を仰ぐ（ヒューマンレビューなので）
- 「イッシューの基準では？」→ GT一致=TP（reachability不問）を確認してから判定
- 「修正済は取り下げて」→ 既修正のPRは即座にclose
- コミットメッセージは英語、理由は具体的に
- PRに「Generated with Claude Code」を入れない
- PRにはPoC（再現コード）を載せる
- イッシューへのレポートは人間が書いた風に
