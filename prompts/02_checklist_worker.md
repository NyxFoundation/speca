
---
Description: [WORKER] Invoke the checklist-specialist skill for a batch of items.
Usage: `/02_checklist_worker WORKER_ID=... QUEUE_FILE=... [TIMESTAMP=...] [ITERATION=...] [BATCH_SIZE=...] [OUTPUT_FILE=...]`
Example: `/02_checklist_worker WORKER_ID=0 QUEUE_FILE=outputs/02_QUEUE_0.json TIMESTAMP=1700000000 ITERATION=1 BATCH_SIZE=5 OUTPUT_FILE=outputs/02_CHECKLIST_PARTIAL_W0_1700000000_1.json`
Language: English only.
Execution hint: This worker prompt is invoked by the phase-02 async orchestrator.
---

<task>
  <goal>For each item in the batch, use the /checklist-specialist skill to generate a security audit checklist from formal properties, then aggregate all checklist items into a single output file.</goal>
  <input type="file" id="queue">{{QUEUE_FILE}}</input>
  <output type="file" id="results">{{OUTPUT_FILE}}</output>

  <critical_requirements>
    **YOU MUST COMPLETE ALL OF THE FOLLOWING:**
    1. Process ALL items in the batch (up to BATCH_SIZE).
    2. Extract and validate checklist items from each skill result.
    3. After processing ALL items, write a JSON file to <ref id="results"/>.
    4. The JSON file MUST be written even if some items fail.

    **FAILURE TO WRITE THE JSON FILE IS A CRITICAL ERROR.**
  </critical_requirements>

  <instructions>
    1. **Initialize**: 
       - Read <ref id="queue"/> and select the first BATCH_SIZE unprocessed items.
       - Create an empty array `all_checklist_items = []`.
       - Create counters: `total_properties = 0`, `total_filtered = 0`, `validation_warnings = 0`.

    2. **Process Each Item**: For each item in the batch:
    
       a. **Invoke Skill**: Call the `/checklist-specialist` skill, passing the property file path.
          The skill returns a JSON object with structure:
          ```json
          {
            "source_file": "...",
            "filtering_summary": {...},
            "checklist": [...],
            "metadata": {...}
          }
          ```
       
       b. **Extract Checklist Items**: From the skill result:
          - Get the `checklist` array from the result.
          - Update counters from `filtering_summary`.
       
       c. **Validate Each Checklist Item**: For each item in `checklist`:
          - **REQUIRED FIELDS CHECK**: Verify ALL of these fields exist and are non-empty:
            - `check_id` (string, format: `CHK-{property_id}-{index}`)
            - `property_id` (string)
            - `title` (string)
            - `severity` (string: Critical/High/Medium/Low/Informational)
            - `mindset` (string: Boundary Guard/Formal Verification Engineer)
            - `is_boundary_check` (boolean)
            - `reachability` (object with `classification`, `entry_points`, `attacker_controlled`, `bug_bounty_scope`)
            - `test_procedure` (string, **MUST NOT be empty**, should have multiple steps)
            - `bug_class` (string)
            - `risk_category` (string)
            - `notes` (string)
          
          - **If validation passes**: Append the item to `all_checklist_items`.
          - **If validation fails**: Log a warning with the missing fields, increment `validation_warnings`, but still append the item (do not discard).
       
       d. **Handle Errors**: If the skill fails entirely for an item:
          - Log the error with the property file path.
          - Continue to the next item (do not abort).

    3. **Write Output File**: After ALL items have been processed, write to <ref id="results"/>:
       ```json
       {
         "checklist": all_checklist_items,
         "metadata": {
           "phase": "02",
           "worker_id": {{WORKER_ID}},
           "batch_index": {{ITERATION}},
           "timestamp": {{TIMESTAMP}},
           "item_count": all_checklist_items.length,
           "total_properties_processed": total_properties,
           "total_filtered": total_filtered,
           "validation_warnings": validation_warnings
         }
       }
       ```
       - This step is **MANDATORY**.
       - The `checklist` key MUST contain the flat array of all checklist items.

    4. **Confirm Completion**: Print a summary:
       ```
       Batch complete: {item_count} checklist items from {batch_size} property files
       Validation warnings: {validation_warnings}
       Output File: {{OUTPUT_FILE}}
       ```
  </instructions>

  <output_schema>
    The output file MUST have this exact structure:
    ```json
    {
      "checklist": [
        {
          "check_id": "CHK-W0B1-235264622-1-001",
          "property_id": "PROP-W0B1-1",
          "title": "...",
          "severity": "Critical|High|Medium|Low|Informational",
          "mindset": "Boundary Guard|Formal Verification Engineer",
          "is_boundary_check": true|false,
          "reachability": {
            "classification": "external-reachable|internal-only|api-only",
            "entry_points": ["P2P", "Transaction", ...],
            "attacker_controlled": true|false,
            "bug_bounty_scope": "in-scope|out-of-scope|conditional"
          },
          "test_procedure": "1. Step one\n2. Step two\n3. Step three...",
          "bug_class": "Input Validation|State Consistency|...",
          "risk_category": "Tampering|Spoofing|...",
          "notes": "Source: PROP-..., ..."
        }
      ],
      "metadata": {
        "phase": "02",
        "worker_id": 0,
        "batch_index": 1,
        "timestamp": 1700000000,
        "item_count": 42,
        "total_properties_processed": 100,
        "total_filtered": 40,
        "validation_warnings": 0
      }
    }
    ```
  </output_schema>

  <data_sources>
    - **Skill**: `/checklist-specialist` — returns checklist items, does NOT write files
    - **Queue File**: Contains items with `property_file` paths pointing to `outputs/01e_PROP_PARTIAL_*.json`
  </data_sources>

  <error_handling>
    - If skill invocation fails: Log error, continue to next item
    - If checklist item validation fails: Log warning, include item anyway
    - If all items fail: Still write output file with empty `checklist` array
    - Never abort the batch due to individual item failures
  </error_handling>
</task>

<output>
  <format>JSON object with `checklist` array and `metadata` object</format>
  <stdout>Max 8 lines: batch size, items processed, validation warnings, short status.</stdout>
  <final_line>Output File: {{OUTPUT_FILE}}</final_line>
</output>
