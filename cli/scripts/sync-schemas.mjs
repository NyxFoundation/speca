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

const __dirname = dirname(fileURLToPath(import.meta.url));
const cliRoot = resolve(__dirname, "..");
const repoRoot = resolve(cliRoot, "..");
const sourceDir = join(repoRoot, "schemas");
const targetDir = join(cliRoot, "src", "lib", "schemas", "generated");

// Whitelist: only the schemas the CLI consumes today. Adding more is cheap
// (just append) but we avoid pulling in the entire orchestrator surface.
const SCHEMA_NAMES = ["TargetInfo.schema.json", "BugBountyScopeInfo.schema.json"];

function fail(message) {
  console.error(`[sync-schemas] ${message}`);
  process.exit(1);
}

if (!existsSync(sourceDir)) {
  fail(`source directory not found: ${sourceDir}\n` +
       `Run \`uv run python scripts/export_schemas.py\` from the repo root first.`);
}

mkdirSync(targetDir, { recursive: true });

const provenance = {
  generated_at: new Date().toISOString(),
  generator: "cli/scripts/sync-schemas.mjs",
  source_dir: "schemas/",
  note: "AUTO-GENERATED — DO NOT EDIT. Run `npm run sync-schemas` to refresh.",
};

const copied = [];
for (const name of SCHEMA_NAMES) {
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

const present = readdirSync(targetDir).sort();
console.log(`[sync-schemas] wrote ${copied.length} schema(s) to ${targetDir}`);
console.log(`[sync-schemas] directory now contains: ${present.join(", ")}`);
