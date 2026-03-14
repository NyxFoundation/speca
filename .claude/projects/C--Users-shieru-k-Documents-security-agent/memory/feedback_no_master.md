---
name: Never touch master branch
description: Absolutely never checkout, merge into, push to, or modify the master branch
type: feedback
---

絶対にmasterブランチに触らないこと。checkout、merge、push、いかなる操作も禁止。

**Why:** ユーザーからの明確な指示。masterはSPECAソースコードのみを管理するブランチであり、監査成果物や作業内容を入れてはならない。
**How to apply:** 作業は常にhiro/*ブランチ上で行う。masterへのcheckout、merge、push、rebaseなどは一切行わない。
