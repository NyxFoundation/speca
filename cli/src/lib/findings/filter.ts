/**
 * filter.ts — tiny query DSL for the M4 finding browser.
 *
 * Grammar (recursive descent, no external parser library):
 *
 *   query   := orExpr
 *   orExpr  := andExpr ( ("OR" | "or") andExpr )*
 *   andExpr := notExpr ( ("AND" | "and" | <whitespace>) notExpr )*
 *   notExpr := ("NOT" | "not" | "-") atom | atom
 *   atom    := "(" orExpr ")"
 *           |  field ":" value
 *           |  bareWord
 *
 * Field names: severity, verdict, prop, repo, text, classification.
 *
 * Values support:
 *   - exact match: `severity:Critical`
 *   - comma-separated OR: `severity:Critical,High`
 *   - wildcard via trailing `*`: `verdict:CONFIRMED_*`, `prop:PROP-6a4*`
 *   - quoted strings for spaces: `text:"valid attack"`
 *
 * Whitespace between atoms = AND. `repo:` matches against any source file
 * path containing the value (substring, case-insensitive). `text:` and
 * bare-word atoms match against the joined haystack (summary/proof/attack/
 * notes/etc.).
 */
import type { Finding } from "./types.js";
import { normaliseSeverity, severityRank } from "./types.js";

// ---- AST ------------------------------------------------------------------

type Node =
  | { kind: "and"; children: Node[] }
  | { kind: "or"; children: Node[] }
  | { kind: "not"; child: Node }
  | { kind: "field"; field: FieldName; values: string[]; raw: string }
  | { kind: "text"; value: string };

const FIELD_NAMES = ["severity", "verdict", "prop", "property", "repo", "text", "classification"] as const;
type FieldName = (typeof FIELD_NAMES)[number];

export interface ParsedFilter {
  ok: true;
  predicate: (f: Finding) => boolean;
  source: string;
  ast: Node | null;
}

export interface FilterError {
  ok: false;
  message: string;
  source: string;
}

export type FilterResult = ParsedFilter | FilterError;

// ---- Tokenizer ------------------------------------------------------------

interface Token {
  type: "word" | "lparen" | "rparen";
  value: string;
}

function tokenize(input: string): Token[] {
  const out: Token[] = [];
  let i = 0;
  const n = input.length;
  while (i < n) {
    const c = input[i];
    if (c === " " || c === "\t" || c === "\n" || c === "\r") {
      i++;
      continue;
    }
    if (c === "(") {
      out.push({ type: "lparen", value: "(" });
      i++;
      continue;
    }
    if (c === ")") {
      out.push({ type: "rparen", value: ")" });
      i++;
      continue;
    }
    if (c === '"' || c === "'") {
      const quote = c;
      let j = i + 1;
      let buf = "";
      while (j < n && input[j] !== quote) {
        if (input[j] === "\\" && j + 1 < n) {
          buf += input[j + 1];
          j += 2;
        } else {
          buf += input[j];
          j++;
        }
      }
      out.push({ type: "word", value: `"${buf}"` });
      i = j + 1;
      continue;
    }
    let j = i;
    let buf = "";
    while (j < n) {
      const ch = input[j];
      if (ch === " " || ch === "\t" || ch === "\n" || ch === "\r" || ch === "(" || ch === ")") break;
      // Quotes inside a word: stop and let the next iteration pick up the quote.
      if (ch === '"' || ch === "'") {
        // unless the quote follows a colon (e.g. text:"foo bar")
        if (input[j - 1] === ":") {
          const quote = ch;
          let k = j + 1;
          let qbuf = "";
          while (k < n && input[k] !== quote) {
            if (input[k] === "\\" && k + 1 < n) {
              qbuf += input[k + 1];
              k += 2;
            } else {
              qbuf += input[k];
              k++;
            }
          }
          buf += `"${qbuf}"`;
          j = k + 1;
          break;
        }
        break;
      }
      buf += ch;
      j++;
    }
    if (buf.length > 0) out.push({ type: "word", value: buf });
    i = j;
  }
  return out;
}

// ---- Parser ---------------------------------------------------------------

class Parser {
  private pos = 0;
  constructor(private readonly tokens: Token[]) {}

  parse(): Node | null {
    if (this.tokens.length === 0) return null;
    const node = this.parseOr();
    if (this.pos !== this.tokens.length) {
      throw new Error(`unexpected token: '${this.tokens[this.pos].value}'`);
    }
    return node;
  }

  private peek(): Token | undefined {
    return this.tokens[this.pos];
  }
  private consume(): Token {
    const t = this.tokens[this.pos];
    this.pos++;
    return t;
  }
  private isKeyword(t: Token | undefined, kw: string): boolean {
    return t?.type === "word" && t.value.toLowerCase() === kw;
  }

  private parseOr(): Node {
    const children: Node[] = [this.parseAnd()];
    while (this.isKeyword(this.peek(), "or")) {
      this.consume();
      children.push(this.parseAnd());
    }
    return children.length === 1 ? children[0] : { kind: "or", children };
  }

  private parseAnd(): Node {
    const children: Node[] = [this.parseNot()];
    while (true) {
      const t = this.peek();
      if (!t) break;
      if (t.type === "rparen") break;
      if (this.isKeyword(t, "or")) break;
      if (this.isKeyword(t, "and")) {
        this.consume();
        children.push(this.parseNot());
        continue;
      }
      // Implicit AND: just another atom.
      children.push(this.parseNot());
    }
    return children.length === 1 ? children[0] : { kind: "and", children };
  }

  private parseNot(): Node {
    const t = this.peek();
    if (!t) throw new Error("unexpected end of input");
    if (this.isKeyword(t, "not") || (t.type === "word" && t.value === "-")) {
      this.consume();
      return { kind: "not", child: this.parseAtom() };
    }
    if (t.type === "word" && t.value.startsWith("-") && t.value.length > 1) {
      // Treat -severity:Foo as NOT severity:Foo.
      this.consume();
      const stripped = t.value.slice(1);
      return { kind: "not", child: this.parseSingleAtom({ ...t, value: stripped }) };
    }
    return this.parseAtom();
  }

  private parseAtom(): Node {
    const t = this.peek();
    if (!t) throw new Error("unexpected end of input");
    if (t.type === "lparen") {
      this.consume();
      const inner = this.parseOr();
      const close = this.peek();
      if (!close || close.type !== "rparen") {
        throw new Error("missing closing paren");
      }
      this.consume();
      return inner;
    }
    return this.parseSingleAtom(this.consume());
  }

  private parseSingleAtom(t: Token): Node {
    if (t.type !== "word") throw new Error(`expected term, got '${t.value}'`);
    const colonIdx = t.value.indexOf(":");
    if (colonIdx > 0 && colonIdx < t.value.length - 1) {
      const fieldRaw = t.value.slice(0, colonIdx).toLowerCase();
      const valueRaw = t.value.slice(colonIdx + 1);
      if ((FIELD_NAMES as readonly string[]).includes(fieldRaw)) {
        const field = (fieldRaw === "property" ? "prop" : fieldRaw) as FieldName;
        const values = splitValues(valueRaw);
        return { kind: "field", field, values, raw: t.value };
      }
    }
    // Bare word (or unrecognised field) — treat as text search.
    return { kind: "text", value: stripQuotes(t.value).toLowerCase() };
  }
}

function splitValues(raw: string): string[] {
  // Allow `severity:Critical,High` or `severity:Critical|High`.
  const stripped = stripQuotes(raw);
  return stripped
    .split(/[,|]/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

function stripQuotes(s: string): string {
  if (s.length >= 2 && (s[0] === '"' || s[0] === "'") && s[s.length - 1] === s[0]) {
    return s.slice(1, -1);
  }
  return s;
}

// ---- Compile to predicate -------------------------------------------------

export function parseFilter(source: string): FilterResult {
  const trimmed = (source ?? "").trim();
  if (trimmed.length === 0) {
    return { ok: true, predicate: () => true, source: trimmed, ast: null };
  }
  let ast: Node | null;
  try {
    const parser = new Parser(tokenize(trimmed));
    ast = parser.parse();
  } catch (err) {
    return { ok: false, source: trimmed, message: (err as Error).message };
  }
  const predicate = compile(ast);
  return { ok: true, predicate, source: trimmed, ast };
}

function compile(node: Node | null): (f: Finding) => boolean {
  if (!node) return () => true;
  switch (node.kind) {
    case "and": {
      const cs = node.children.map(compile);
      return (f) => cs.every((c) => c(f));
    }
    case "or": {
      const cs = node.children.map(compile);
      return (f) => cs.some((c) => c(f));
    }
    case "not": {
      const c = compile(node.child);
      return (f) => !c(f);
    }
    case "field":
      return compileField(node);
    case "text":
      return (f) => f.searchHaystack.includes(node.value);
  }
}

function compileField(node: Extract<Node, { kind: "field" }>): (f: Finding) => boolean {
  const matchers = node.values.map((v) => buildValueMatcher(v));
  switch (node.field) {
    case "severity":
      return (f) => {
        const sev = f.severity || normaliseSeverity(f.rawSeverity);
        if (!sev) return false;
        return matchers.some((m) => m(sev) || m(sev.toLowerCase()) || m(String(severityRank(sev))));
      };
    case "verdict":
      return (f) => matchers.some((m) => m(f.verdict));
    case "classification":
      return (f) => matchers.some((m) => m(f.classification));
    case "prop":
    case "property":
      return (f) => matchers.some((m) => m(f.propertyId));
    case "repo":
      return (f) =>
        f.sourceFiles.some((src) => matchers.some((m) => m(src))) ||
        (f.primaryLocation ? matchers.some((m) => m(f.primaryLocation!.file)) : false);
    case "text":
      return (f) => matchers.some((m) => m(f.searchHaystack));
  }
}

function buildValueMatcher(rawValue: string): (target: string) => boolean {
  const value = rawValue.trim();
  if (value.length === 0) return () => true;
  // Wildcard at end (most common): CONFIRMED_*
  if (value.includes("*") || value.includes("?")) {
    // Translate the user-typed glob into a regex, escaping every meta char
    // EXCEPT `*` and `?` (which we map to `.*` and `.`).
    let body = "";
    for (const ch of value) {
      if (ch === "*") body += ".*";
      else if (ch === "?") body += ".";
      else body += escapeRegex(ch);
    }
    const pattern = new RegExp(`^${body}$`, "i");
    return (target) => pattern.test(target ?? "");
  }
  // Exact match (case-insensitive) for short tokens; substring for longer
  // multi-word values typed via `text:`.
  const lower = value.toLowerCase();
  return (target) => {
    if (target == null) return false;
    const t = target.toLowerCase();
    if (t === lower) return true;
    // Allow substring match when the user typed multi-word / underscore style
    // values — e.g. `verdict:CONFIRMED_VULN` should also match `CONFIRMED_VULNERABILITY`.
    if (t.includes(lower)) return true;
    return false;
  };
}

function escapeRegex(s: string): string {
  return s.replace(/[.+^${}()|[\]\\]/g, "\\$&");
}

// ---- Convenience ----------------------------------------------------------

export function applyFilter(findings: Finding[], source: string): {
  matched: Finding[];
  result: FilterResult;
} {
  const result = parseFilter(source);
  if (!result.ok) return { matched: findings, result };
  return { matched: findings.filter(result.predicate), result };
}
