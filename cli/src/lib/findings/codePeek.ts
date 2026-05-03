/**
 * codePeek.ts — read a window of source from a file referenced by a finding.
 *
 * The browser invokes `loadCodePeek` lazily when the user presses `c`; failure
 * (file not found, decoding error, line range out of range) is non-fatal and
 * surfaces as a `message` so the panel can render a hint.
 */
import { promises as fs } from "node:fs";
import { extname, isAbsolute, resolve } from "node:path";

import type { CodeLocationLite } from "./types.js";

export interface CodePeek {
  ok: true;
  filePath: string;
  language: string;
  startLine: number;
  endLine: number;
  lines: string[];
}

export interface CodePeekError {
  ok: false;
  filePath: string;
  message: string;
}

export type CodePeekResult = CodePeek | CodePeekError;

export interface PeekOptions {
  /** Base dir used to resolve relative file paths. Defaults to process cwd. */
  cwd?: string;
  /** Padding lines on either side of the location range. */
  padding?: number;
  /** Hard cap on lines returned, to keep TUI responsive on huge files. */
  maxLines?: number;
}

const DEFAULT_PADDING = 4;
const DEFAULT_MAX_LINES = 60;

export async function loadCodePeek(
  loc: CodeLocationLite | null,
  options: PeekOptions = {},
): Promise<CodePeekResult> {
  if (!loc || !loc.file) {
    return { ok: false, filePath: "", message: "no code location" };
  }
  const cwd = options.cwd ?? process.cwd();
  const padding = options.padding ?? DEFAULT_PADDING;
  const maxLines = options.maxLines ?? DEFAULT_MAX_LINES;
  const filePath = isAbsolute(loc.file) ? loc.file : resolve(cwd, loc.file);
  let raw: string;
  try {
    raw = await fs.readFile(filePath, "utf8");
  } catch (err) {
    return { ok: false, filePath, message: `read failed: ${(err as Error).message}` };
  }
  const allLines = raw.split(/\r?\n/);
  const start = Math.max(1, (loc.startLine || 1) - padding);
  const requestedEnd = loc.endLine || loc.startLine || allLines.length;
  const end = Math.min(allLines.length, requestedEnd + padding, start + maxLines - 1);
  const lines = allLines.slice(start - 1, end);
  return {
    ok: true,
    filePath,
    language: detectLanguage(filePath),
    startLine: start,
    endLine: end,
    lines,
  };
}

const EXT_TO_LANG: Record<string, string> = {
  ".ts": "typescript",
  ".tsx": "typescript",
  ".js": "javascript",
  ".jsx": "javascript",
  ".mjs": "javascript",
  ".cjs": "javascript",
  ".py": "python",
  ".go": "go",
  ".rs": "rust",
  ".rb": "ruby",
  ".java": "java",
  ".kt": "kotlin",
  ".sol": "solidity",
  ".c": "c",
  ".h": "c",
  ".cc": "cpp",
  ".cpp": "cpp",
  ".hpp": "cpp",
  ".cs": "cs",
  ".php": "php",
  ".sh": "bash",
  ".bash": "bash",
  ".json": "json",
  ".yaml": "yaml",
  ".yml": "yaml",
  ".md": "markdown",
  ".html": "html",
  ".css": "css",
};

export function detectLanguage(filePath: string): string {
  return EXT_TO_LANG[extname(filePath).toLowerCase()] ?? "plaintext";
}
