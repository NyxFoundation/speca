
---
Description: [WORKER] Invoke the audit-reviewer skill for a batch of items.
Usage: `/04_review_worker WORKER_ID=... QUEUE_FILE=... [TIMESTAMP=...] [ITERATION=...] [BATCH_SIZE=...] [OUTPUT_FILE=...]`
Example: `/04_review_worker WORKER_ID=0 QUEUE_FILE=outputs/04_QUEUE_0.json TIMESTAMP=1700000000 ITERATION=1 BATCH_SIZE=5 OUTPUT_FILE=outputs/04_PARTIAL_W0_1700000000_1.json`
Language: English only.
Execution hint: This worker prompt is invoked by the phase-04 async orchestrator.
---

<task>
  <goal>For each item in the batch, use the /audit-reviewer skill to review and validate formal audit findings.</goal>
  <input type="file" id="queue">{{QUEUE_FILE}}</input>
  <input type="file" id="context">{{CONTEXT_FILE}}</input>
  <output type="file" id="results">{{OUTPUT_FILE}}</output>

  <critical_requirements>
    **YOU MUST COMPLETE ALL OF THE FOLLOWING:**
    1. Process ALL items in the batch (up to BATCH_SIZE).
    2. After processing ALL items, write a JSON file to <ref id="results"/>.
    3. The JSON file MUST be written even if some items fail.

    **FAILURE TO WRITE THE JSON FILE IS A CRITICAL ERROR.**
  </critical_requirements>

  <instructions>
    1. **Initialize**: Read <ref id="queue"/> to get `item_ids` and `context_file` path. Read <ref id="context"/> to get item data (keyed by ID). For each ID in `item_ids`, look up the item data in context. Create an empty list `all_reviewed = []`.

    2. **Process Each Item**: For each item in the batch:
       a. **Invoke Skill**: Call the `/audit-reviewer` skill, passing the audit result from Phase 03.
       b. **Handle Errors**: If the skill fails, create an error object for that item.
       c. **Collect Result**: Append the successful result or the error object to `all_reviewed`.

    3. **Write Output File**: After ALL items have been processed, write a **single JSON object** to <ref id="results"/>:
       ```json
       {
         "reviewed_items": [ ...all_reviewed... ],
         "metadata": { "phase": "04", "total_reviewed": N, "timestamp": "..." }
       }
       ```
       - The top-level structure MUST be a **JSON object** (dict), NOT a JSON array.
       - `"reviewed_items"` MUST be the key containing the flat list of all reviewed item objects.
       - This step is **MANDATORY**.

    4. **Confirm Completion**: Print a summary and end with: `Output File: {{OUTPUT_FILE}}`
  </instructions>

  <data_sources>
    - **Skill**: `/audit-reviewer`
    - **Queue File**: Contains `item_ids` and `context_file` path. Read the context file to get item data keyed by ID, each with the audit result from Phase 03.
    - **MCP Tools**: `mcp__filesystem__read_multiple_files` for batch loading audit results.
  </data_sources>
</task>

<output>
  <format>JSON object with "reviewed_items" key (NOT a JSON array)</format>
  <stdout>Max 8 lines: batch size, items processed, short status.</stdout>
  <final_line>Output File: {{OUTPUT_FILE}}</final_line>
</output>
