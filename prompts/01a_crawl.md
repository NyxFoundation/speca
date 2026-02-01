
---
Description: Recursively crawl all specification documents starting from the provided SPEC_URLS. Discover all unique, relevant specification URLs (EIPs, RFCs, design documents) and create a work queue for the extraction stage. This ensures 100% coverage of the specification landscape.
Usage: `/01a_crawl KEYWORDS=... SPEC_URLS=... APPEND_MODE=...`
Example: `/01a_crawl KEYWORDS="geth,ethereum client,EIP,blockchain" SPEC_URLS="https://ethereum.org/en/developers/docs/,https://eips.ethereum.org/" APPEND_MODE=false`
Language: English only.
Execution hint: This is the first step. Run this before `/01b_extract`. It creates the work queue for iterative processing.
---
**Always use /serena for development tasks to keep the workflow efficient.**

# **System Specification - Stage 1: Discovery & Queuing**

**Goal**
Recursively crawl all specification documents starting from the provided `SPEC_URLS`. The primary goal is to discover all unique, relevant specification URLs (like EIPs, RFCs, design documents) and create a work queue for the next stage. This ensures 100% coverage of the specification landscape.

**Output (required file):** `outputs/01a_STATE.json`

---

## 1) Inputs

1.  **`KEYWORDS`**: A comma-separated list of keywords to filter relevant links during crawling.
2.  **`SPEC_URLS`**: A comma-separated list of initial, top-level specification URLs provided by the user.
3.  **`APPEND_MODE`** (optional): If set to `true`, merge newly discovered URLs with the existing `outputs/01a_STATE.json` instead of overwriting it.

---

## 2) Discovery & Queuing Logic

### **Task 2.1: Load Existing State (if APPEND_MODE=true)**

**If `APPEND_MODE` is `true`:**
1.  Read the existing `outputs/01a_STATE.json` file.
2.  Extract the current `work_queue` and `processed_urls` lists.
3.  Initialize `discovered_urls` with all URLs from both `work_queue` and `processed_urls` to avoid duplicates.

**If `APPEND_MODE` is not `true` or the file doesn't exist:**
1.  Initialize `discovered_urls` as an empty set.

### **Task 2.2: Recursive URL Crawling**

1.  Initialize `urls_to_visit` and ensure `discovered_urls` is set from Task 2.1.
2.  Add all `SPEC_URLS` to the `urls_to_visit` queue.
3.  **Loop until `urls_to_visit` is empty:**
    a.  Dequeue a URL.
    b.  If this URL is already in `discovered_urls`, continue to the next URL.
    c.  Add the URL to `discovered_urls`.
    d.  Visit the URL and parse its content for all hyperlink (`<a>`) tags.
    e.  For each found link:
        i.  Resolve it to an absolute URL.
        ii. If the URL points to a relevant specification domain (e.g., `eips.ethereum.org`, `github.com/.../specs`) or contains any of the `KEYWORDS`, add it to the `urls_to_visit` queue.

### **Task 2.3: Create or Update the State File**

**If `APPEND_MODE` is `true`:**
1.  Merge the newly discovered URLs with the existing `work_queue`.
2.  Remove duplicates.
3.  Keep the existing `processed_urls` unchanged.
4.  Update the `metadata.total_discovered` count.
5.  Add a new field `metadata.appended_at` with the current timestamp.

**If `APPEND_MODE` is not `true`:**
1.  Create a new `outputs/01a_STATE.json` with:
    *   **`work_queue`**: The complete list of `discovered_urls`.
    *   **`processed_urls`**: An empty list `[]`.

---

## 3) Required Output Format (JSON)

**File:** `outputs/01a_STATE.json`

### Normal Mode (APPEND_MODE=false or not set)

```json
{
  "metadata": {
    "crawled_at": "2025-01-16T12:00:00Z",
    "keywords": ["geth", "ethereum client", "EIP", "blockchain"],
    "initial_spec_urls": ["https://ethereum.org/en/developers/docs/"],
    "total_discovered": 152
  },
  "work_queue": [
    "https://eips.ethereum.org/EIPS/eip-1559",
    "https://eips.ethereum.org/EIPS/eip-2718",
    "https://eips.ethereum.org/EIPS/eip-2930",
    "https://eips.ethereum.org/EIPS/eip-3198",
    "https://eips.ethereum.org/EIPS/eip-4844"
  ],
  "processed_urls": []
}
```

### Append Mode (APPEND_MODE=true)

```json
{
  "metadata": {
    "crawled_at": "2025-01-16T12:00:00Z",
    "appended_at": "2025-01-16T15:30:00Z",
    "keywords": ["geth", "ethereum client", "EIP", "blockchain", "consensus specs"],
    "initial_spec_urls": ["https://ethereum.org/en/developers/docs/", "https://github.com/ethereum/consensus-specs"],
    "total_discovered": 198
  },
  "work_queue": [
    "https://eips.ethereum.org/EIPS/eip-1559",
    "https://eips.ethereum.org/EIPS/eip-2718",
    "https://github.com/ethereum/consensus-specs/blob/dev/specs/phase0/beacon-chain.md",
    "https://github.com/ethereum/consensus-specs/blob/dev/specs/altair/beacon-chain.md"
  ],
  "processed_urls": [
    "https://eips.ethereum.org/EIPS/eip-1559"
  ]
}
```
