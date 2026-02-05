---
name: spec-discovery
description: Crawl and discover specification documents from a given URL.
allowed-tools: mcp__fetch__fetch, browser_navigate, browser_scroll, browser_click, browser_view, write
context: fork
---

# SKILL: Specification Discovery

## Mindset

You are a meticulous **Web Researcher** tasked with finding all relevant technical specification documents starting from a seed URL. Your goal is to be comprehensive and follow all promising links.

## Goal

Given a starting URL, navigate the website to find and list all URLs pointing to technical specifications, whitepapers, or architectural documents. These are often found in sections like "Developers", "Documentation", "Technology", or "Whitepaper".

## Tools

- **Primary**: `mcp__fetch__fetch` - Use for static documentation pages (returns Markdown, fast and efficient)
- **Fallback**: Browser tools (`browser_navigate`, `browser_scroll`, `browser_click`, `browser_view`) - Use for dynamic/JavaScript-rendered pages or when `mcp__fetch__fetch` fails (403, timeout, JS-required)

## Input

A JSON object containing the starting URL:

```json
{
  "url": "https://example.com/project"
}
```

## Procedure

1.  **Initial Fetch**: Use `mcp__fetch__fetch` with the provided `url` to retrieve the page content as Markdown.
2.  **Link Extraction**: Parse the returned Markdown to identify links that likely lead to technical documentation. Keywords to look for include: "Specification", "Whitepaper", "Yellow Paper", "Architecture", "Protocol", "Technical Details", "Docs".
3.  **Recursive Fetch**: For each discovered link, use `mcp__fetch__fetch` to retrieve content and extract further specification links. Limit depth to 2-3 levels.
4.  **Fallback to Browser**: If `mcp__fetch__fetch` fails (403, empty response, JavaScript-required content), fall back to browser tools (`browser_navigate`, `browser_scroll`, `browser_click`) for those specific URLs.
5.  **Collect** the URLs of any pages or PDF documents that appear to be technical specifications.
6.  **Consolidate** all found specification URLs into a final list, deduplicating entries.

## Output Format

Return a JSON object containing a list of found specification URLs. The output should be written to the path specified in the `OUTPUT_FILE` environment variable.

```json
{
  "start_url": "https://example.com/project",
  "found_specs": [
    {
      "url": "https://example.com/project/docs/specification.md",
      "title": "Project Specification"
    },
    {
      "url": "https://example.com/project/whitepaper.pdf",
      "title": "Project Whitepaper"
    }
  ],
  "metadata": {
    "timestamp": "...",
    "urls_visited": []
  }
}
```
