
---
Description: [WORKER] Invoke the checklist-specialist skill for a batch of items.
Usage: `/02_checklist_worker WORKER_ID=... QUEUE_FILE=... [TIMESTAMP=...] [ITERATION=...] [BATCH_SIZE=...] [OUTPUT_FILE=...]`
Example: `/02_checklist_worker WORKER_ID=0 QUEUE_FILE=outputs/02_QUEUE_0.json TIMESTAMP=1700000000 ITERATION=1 BATCH_SIZE=5 OUTPUT_FILE=outputs/02_CHECKLIST_PARTIAL_W0_1700000000_1.json`
Language: English only.
Execution hint: This worker prompt is invoked by the phase-02 async orchestrator.
---

<task>
  <goal>For each item in the batch, use the /checklist-specialist skill to generate a security audit checklist from formal properties.</goal>
  <input type="file" id="queue">{{QUEUE_FILE}}</input>
  <output type="file" id="results">{{OUTPUT_FILE}}</output>

  <critical_requirements>
    **YOU MUST COMPLETE ALL OF THE FOLLOWING:**
    1. Process ALL items in the batch (up to BATCH_SIZE).
    2. After processing ALL items, write a JSON file to <ref id="results"/>.
    3. The JSON file MUST be written even if some items fail.

    **FAILURE TO WRITE THE JSON FILE IS A CRITICAL ERROR.**
  </critical_requirements>

  <instructions>
    1. **Initialize**: Read <ref id="queue"/> and select the first BATCH_SIZE unprocessed items. Create an empty array `results = []`.

    2. **Process Each Item**: For each item in the batch:
       a. **Invoke Skill**: Call the `/checklist-specialist` skill, passing the path to the property file.
       b. **Handle Errors**: If the skill fails, create an error object for that item.
       c. **Append Result**: Append the successful result or the error object to the `results` array.

    3. **Write Output File**: After ALL items have been processed, write the `results` array to <ref id="results"/>.
       - This step is **MANDATORY**.

    4. **Confirm Completion**: Print a summary and end with: `Output File: {{OUTPUT_FILE}}`
  </instructions>

  <data_sources>
    - **Skill**: `/checklist-specialist`
    - **Queue File**: Contains items with `property_file` paths.
  </data_sources>
</task>

<output>
  <format>JSON array</format>
  <stdout>Max 8 lines: batch size, items processed, short status.</stdout>
  <final_line>Output File: {{OUTPUT_FILE}}</final_line>
</output>
