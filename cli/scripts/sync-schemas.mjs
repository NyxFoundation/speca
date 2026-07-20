#!/usr/bin/env node
/**
 * sync-schemas.mjs
 *
 * Copies the JSON Schema files emitted by `scripts/export_schemas.py` (U2)
 * from the repository root `schemas/` directory into
 * `cli/src/lib/schemas/generated/` so they can be bundled with the
 * speca-cli npm package and validated at runtime via Ajv.
 *
 * The runtime CLI reads only the embedded copies; the originals at the
 * repo root remain the source of truth.
 *
 * AUTO-GENERATED OUTPUT — DO NOT EDIT THE FILES IN generated/.
 * Run `npm run sync-schemas` to refresh them.
 */
import { readFileSync, writeFileSync, mkdirSync, readdirSync, existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { compile as compileJsonSchemaToTs } from "json-schema-to-typescript";
import { jsonSchemaToZod } from "json-schema-to-zod";

const __dirname = dirname(fileURLToPath(import.meta.url));
const cliRoot = resolve(__dirname, "..");
const repoRoot = resolve(cliRoot, "..");
const sourceDir = join(repoRoot, "schemas");
const targetDir = join(cliRoot, "src", "lib", "schemas", "generated");

// Whitelist: only the schemas the CLI consumes today. Adding more is cheap
// (just append) but we avoid pulling in the entire orchestrator surface.
const SCHEMA_NAMES = ["TargetInfo.schema.json", "BugBountyScopeInfo.schema.json"];

// NDJSON pipeline event schemas — separate list so we can codegen Zod for
// them (the artefact schemas above are validated via Ajv and don't need
// Zod). Order is fixed to keep the generated Zod union member order stable
// across machines.
const EVENT_SCHEMA_NAMES = [
  "PipelineStartedEvent.schema.json",
  "PhaseStartedEvent.schema.json",
  "PhaseCompletedEvent.schema.json",
  "PhaseFailedEvent.schema.json",
  "BudgetExceededEvent.schema.json",
  "CircuitBreakerTrippedEvent.schema.json",
  "PipelineCompletedEvent.schema.json",
  "WarningEvent.schema.json",
];

function fail(message) {
  console.error(`[sync-schemas] ${message}`);
  process.exit(1);
}

if (!existsSync(sourceDir)) {
  fail(`source directory not found: ${sourceDir}\n` +
       `Run \`uv run python scripts/export_schemas.py\` from the repo root first.`);
}

mkdirSync(targetDir, { recursive: true });

// Provenance is intentionally timestamp-free so re-running sync-schemas on
// an unchanged source tree yields a byte-identical output. CI relies on
// `git diff --exit-code` to detect drift; a wall-clock field would defeat
// that check. Use `git log` for "when was this regenerated".
const provenance = {
  generator: "cli/scripts/sync-schemas.mjs",
  source_dir: "schemas/",
  note: "AUTO-GENERATED — DO NOT EDIT. Run `npm run sync-schemas` to refresh.",
};

const copied = [];
function copySchema(name) {
  const src = join(sourceDir, name);
  if (!existsSync(src)) {
    fail(`expected schema not found: ${src}`);
  }
  const raw = readFileSync(src, "utf8");
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch (err) {
    fail(`failed to parse ${src}: ${err.message}`);
  }
  // JSON cannot carry comments; record provenance in a structured field.
  parsed._generated = provenance;
  const dst = join(targetDir, name);
  writeFileSync(dst, `${JSON.stringify(parsed, null, 2)}\n`, "utf8");
  copied.push(name);
  return parsed;
}

for (const name of SCHEMA_NAMES) {
  copySchema(name);
}

// Events: copied into a sibling directory and used as the source of the
// auto-generated Zod schemas + TS types.
const eventsTargetDir = join(targetDir, "events");
mkdirSync(eventsTargetDir, { recursive: true });
const eventSchemas = [];
for (const name of EVENT_SCHEMA_NAMES) {
  const src = join(sourceDir, name);
  if (!existsSync(src)) {
    fail(`expected event schema not found: ${src}`);
  }
  const parsed = JSON.parse(readFileSync(src, "utf8"));
  parsed._generated = provenance;
  writeFileSync(
    join(eventsTargetDir, name),
    `${JSON.stringify(parsed, null, 2)}\n`,
    "utf8",
  );
  eventSchemas.push({ name, parsed });
}

// Write a tiny README.md alongside the generated JSON to make the directory
// self-documenting for anyone browsing the source tree.
const readmePath = join(targetDir, "README.md");
const readme = [
  "# Generated JSON Schemas",
  "",
  "AUTO-GENERATED — DO NOT EDIT.",
  "",
  "These files are copied from the repository root `schemas/` directory by",
  "`cli/scripts/sync-schemas.mjs` (run via `npm run sync-schemas`).",
  "",
  "The originals are produced by `scripts/export_schemas.py` from the Pydantic",
  "models in `scripts/orchestrator/schemas.py` and are the single source of",
  "truth.",
  "",
  "## Files",
  "",
  ...copied.map((n) => `- \`${n}\``),
  "",
].join("\n");
writeFileSync(readmePath, readme, "utf8");

// Ensure the directory is git-tracked (vitest expectations) by writing an
// index file referencing each schema. This is a simple manifest, not a
// hand-maintained file.
const manifestPath = join(targetDir, "manifest.json");
writeFileSync(
  manifestPath,
  `${JSON.stringify({ schemas: copied, _generated: provenance }, null, 2)}\n`,
  "utf8",
);

// Generate TypeScript interfaces from each JSON Schema so the `*Input`
// shapes consumed by `lib/schemas/index.ts` cannot drift away from the
// Pydantic-derived JSON Schema. The generated file is committed (so a
// fresh checkout doesn't need to run sync-schemas before tsc) and refreshed
// from `npm run build`.
//
// `additionalProperties: false` here is intentional: it forces the
// generated interface to omit the catch-all `[k: string]: unknown` index
// signature, so renaming a Pydantic field surfaces as a missing key in
// every TS literal that builds one — that is the drift signal we want.
// Wizards that legitimately attach extra fields (project_name, etc.) use
// intersection types at the call site instead of leaning on the index sig.
const tsCompileOpts = {
  bannerComment: [
    "/**",
    " * AUTO-GENERATED — DO NOT EDIT.",
    " * Source: schemas/<Name>.schema.json (Pydantic-derived).",
    " * Run `npm run sync-schemas` to refresh.",
    " */",
    "",
  ].join("\n"),
  additionalProperties: false,
  style: { singleQuote: false, semi: true },
  declareExternallyReferenced: true,
  unreachableDefinitions: false,
};

const generatedTsParts = [];
for (const name of copied) {
  const src = join(sourceDir, name);
  const raw = JSON.parse(readFileSync(src, "utf8"));
  // Strip our provenance bookkeeping before handing to the codegen; it's a
  // non-standard root key that confuses the type compiler.
  delete raw._generated;
  const ts = await compileJsonSchemaToTs(raw, raw.title ?? name, tsCompileOpts);
  generatedTsParts.push(ts.trim());
}
const tsHeader = [
  "/**",
  " * AUTO-GENERATED type aliases derived from the JSON Schemas in this directory.",
  " * Edit the Pydantic models in `scripts/orchestrator/schemas.py` and",
  " * regenerate via `npm run sync-schemas`.",
  " */",
  "",
].join("\n");
const tsPath = join(targetDir, "types.ts");
writeFileSync(tsPath, tsHeader + generatedTsParts.join("\n\n") + "\n", "utf8");

// Codegen Zod schemas + a discriminated union for pipeline events.
// `json-schema-to-zod` handles the per-event shape; we hand-roll the union
// at the end because the library doesn't know which event types should be
// merged into one z.discriminatedUnion.
const eventTsLines = [
  "/**",
  " * AUTO-GENERATED — DO NOT EDIT.",
  " * Source: schemas/events/*.schema.json (Pydantic-derived).",
  " * Run `npm run sync-schemas` to refresh.",
  " */",
  "",
  "import { z } from \"zod\";",
  "",
];
const eventVarNames = [];
for (const { name, parsed } of eventSchemas) {
  // Strip provenance + JSON Schema $defs the codegen does not need.
  const cleaned = { ...parsed };
  delete cleaned._generated;
  // Pydantic emits the discriminator with a `default`, which makes
  // json-schema-to-zod render it as `.optional()`. Strip the default and
  // ensure `type` is in `required` so the generated Zod treats it as
  // mandatory — z.discriminatedUnion needs each member's discriminator to
  // be a non-optional literal.
  if (cleaned.properties?.type) {
    delete cleaned.properties.type.default;
    cleaned.required = Array.from(new Set([...(cleaned.required ?? []), "type"]));
  }
  const zodCode = jsonSchemaToZod(cleaned, { module: "none", name: undefined });
  // The exported variable name uses the schema title (e.g. PhaseStartedEvent).
  const varName = parsed.title ?? name.replace(/\.schema\.json$/, "");
  eventTsLines.push(`export const ${varName}Schema = ${zodCode};`);
  eventTsLines.push(
    `export type ${varName} = z.infer<typeof ${varName}Schema>;`,
  );
  eventTsLines.push("");
  eventVarNames.push(varName);
}
eventTsLines.push("export const pipelineEventSchema = z.discriminatedUnion(\"type\", [");
for (const v of eventVarNames) {
  // The codegen emits objects with `passthrough()`; that disables the
  // discriminated-union shortcut, so we rewrap as `.passthrough()` outside
  // the union builder. Easier path: use `z.union(...)` instead. We keep
  // discriminatedUnion for narrowing speed and accept the constraint that
  // event objects are emitted via `.strict()`-style bodies.
  eventTsLines.push(`  ${v}Schema,`);
}
eventTsLines.push("] as const);");
eventTsLines.push("export type PipelineEvent = z.infer<typeof pipelineEventSchema>;");
eventTsLines.push("");

const eventsTsPath = join(eventsTargetDir, "schemas.ts");
writeFileSync(eventsTsPath, eventTsLines.join("\n"), "utf8");

const present = readdirSync(targetDir).sort();
console.log(`[sync-schemas] wrote ${copied.length} schema(s) + types.ts to ${targetDir}`);
console.log(`[sync-schemas] wrote ${eventSchemas.length} event schema(s) + schemas.ts to ${eventsTargetDir}`);
console.log(`[sync-schemas] directory now contains: ${present.join(", ")}`);
