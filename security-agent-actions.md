# Security Agent CI/CD Actions Design

## Overview

This document describes the CI/CD pipeline design for automating the whitehat security analysis workflow using GitHub Actions, Claude Code Actions, and GitHub Copilot.

## Pipeline Architecture

```
┌─────────────┐
│  Step 1     │ → SPEC Generation
│ (01_SPEC)   │   Claude Code Actions
└─────┬───────┘
      │
┌─────▼───────┐
│  Step 2     │ → AUDITMAP Generation  
│(02_AUDITMAP)│   Claude Code Actions
└─────┬───────┘
      │
┌─────▼───────┐
│ Step 2b     │ → JSON Review
│(Copilot Rev)│   GitHub Copilot
└─────┬───────┘
      │
┌─────▼───────┐ ┌─────────────┐
│ Step 3a     │ │  Step 3b    │ → PoC Generation (Parallel)
│(POC_UNIT)   │ │(POC_INTEGR) │   Per Vulnerability
└─────┬───────┘ └──────┬──────┘
      │                 │
      └────────┬────────┘
               │
         ┌─────▼───────┐
         │  Step 4     │ → Report Generation
         │ (REPORT)    │   + Discord Notification
         └─────────────┘
```

## Job Definitions

### Job 1: SPEC Generation
**Purpose**: Generate comprehensive specification from target directory

**Implementation**:
- Executes `prompts/whitehat/01_SPEC.md` via Claude Code Actions
- Inputs:
  - `TARGET_DIRECTORY`: From environment variable or workflow input
  - Repository documentation and source code
- Outputs:
  - `outputs/WHITEHAT_01_SPEC.json`
- Artifacts:
  - Specification JSON for downstream jobs

### Job 2: AUDITMAP Generation  
**Purpose**: Analyze code and generate vulnerability audit map

**Implementation**:
- Executes `prompts/whitehat/02_AUDITMAP.md` via Claude Code Actions
- Dependencies: Job 1 artifacts
- Inputs:
  - `WHITEHAT_01_SPEC.json` from previous job
  - Target source code
  - Known vulnerability databases
- Outputs:
  - Source code with `@audit` and `@audit-ok` annotations
  - `outputs/WHITEHAT_02_AUDITMAP.json`
- Artifacts:
  - Audit map JSON for review and PoC generation

### Job 2b: Copilot Review
**Purpose**: Validate and score vulnerabilities using GitHub Copilot

**Implementation**:
- Uses GitHub Copilot API to review `WHITEHAT_02_AUDITMAP.json`
- Review criteria:
  - Vulnerability validity
  - Risk severity assessment
  - False positive detection
- Outputs:
  - Reviewed audit map with confidence scores
  - Go/No-go decision for each vulnerability
- Gates:
  - Only vulnerabilities with score > threshold proceed to PoC

### Job 3: Parallel PoC Generation
**Purpose**: Generate proof-of-concept for each validated vulnerability

**Implementation**:
- Dynamic matrix strategy based on vulnerability list
- Parallel execution for each vulnerability
- Two sub-jobs:
  - **3a: Unit PoC** (`prompts/whitehat/03a_POC_UNIT.md`)
  - **3b: Integration PoC** (`prompts/whitehat/03b_POC_INTEGRATION.md`)
- Inputs:
  - Individual vulnerability from reviewed audit map
  - `VULN_NAME` as matrix parameter
- Outputs:
  - PoC test files
  - Execution results
- Resource limits:
  - Max parallel jobs: 10
  - Timeout per PoC: 30 minutes

### Job 4: Report Generation & Notification
**Purpose**: Aggregate results and notify stakeholders

**Implementation**:
- Executes `prompts/whitehat/04_REPORT.md` via Claude Code Actions
- Dependencies: All Job 3 artifacts
- Actions:
  - Aggregate all PoC results
  - Generate comprehensive security report
  - Send Discord notification
- Outputs:
  - `outputs/WHITEHAT_04_REPORT.json`
  - Markdown formatted report
- Notifications:
  - Discord webhook with summary
  - Link to full report artifacts

## Technical Implementation Details

### Claude Code Actions Integration

**Setup Requirements**:
1. Register as GitHub App
2. Configure permissions:
   - Repository contents: Read/Write
   - Actions: Write
   - Issues: Write (for comments)

**API Configuration**:
```yaml
env:
  CLAUDE_API_KEY: ${{ secrets.CLAUDE_API_KEY }}
  CLAUDE_MODEL: claude-3-opus-20240229
  CLAUDE_MAX_TOKENS: 100000
```

**Rate Limiting**:
- Implement exponential backoff
- Queue management for API calls
- Fallback to manual trigger on quota exceeded

### Dynamic Prompt Variable Substitution

**Template Variables**:
- `{{TARGET_DIRECTORY}}`: Repository root or specified target
- `{{AUDIT_ORDER_FILE}}`: Path to audit ordering configuration
- `{{VULN_NAME}}`: Individual vulnerability identifier
- `{{OUTPUT_TEST_PATH}}`: PoC output location

**Substitution Process**:
1. Load prompt template from markdown file
2. Replace variables with runtime values
3. Submit to Claude Code Actions API
4. Parse structured JSON output

### Parallel Execution Strategy

**Matrix Generation**:
```yaml
strategy:
  matrix:
    vulnerability: ${{ fromJson(needs.copilot-review.outputs.validated_vulns) }}
  max-parallel: 10
```

**Resource Optimization**:
- Group similar vulnerabilities
- Priority queue based on severity
- Automatic retry on transient failures

### Security Considerations

**Secrets Management**:
- `CLAUDE_API_KEY`: Claude API access
- `GITHUB_TOKEN`: Repository operations
- `DISCORD_WEBHOOK`: Notification endpoint
- `COPILOT_API_KEY`: GitHub Copilot access

**Output Security**:
- Encrypt sensitive findings
- Restricted artifact access
- Sanitized public notifications

**Execution Isolation**:
- Sandboxed PoC execution
- No network access during PoC runs
- Resource limits enforcement

## Workflow Triggers

**Automatic Triggers**:
- Pull request to main branch
- Weekly scheduled scan
- Security advisory publication

**Manual Triggers**:
```yaml
workflow_dispatch:
  inputs:
    target_repository:
      description: 'Target repository URL'
      required: true
    analysis_depth:
      description: 'Analysis depth'
      type: choice
      options:
        - quick
        - standard
        - comprehensive
```

## Error Handling

**Failure Modes**:
1. **API Quota Exceeded**: Queue for retry or manual intervention
2. **PoC Timeout**: Mark as inconclusive, continue pipeline
3. **Invalid JSON Output**: Validation error, request regeneration
4. **Copilot Rejection**: Skip to manual review queue

**Recovery Strategy**:
- Checkpoint after each major step
- Partial result aggregation
- Manual override capability

## Monitoring and Metrics

**Key Metrics**:
- Pipeline execution time
- Vulnerabilities discovered per scan
- False positive rate (post-human review)
- API usage and costs

**Dashboards**:
- GitHub Actions summary
- Discord monitoring channel
- Cost tracking spreadsheet

## Future Enhancements

1. **Multi-language Support**: Extend beyond Solidity/JS
2. **Custom Agent Training**: Fine-tune on project-specific patterns
3. **Automated Patch Generation**: Generate fixes for discovered vulnerabilities
4. **Integration with Bug Bounty Platforms**: Auto-submit validated findings