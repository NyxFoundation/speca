# speca-cli

> v0.9.2 (soft launch ahead of v1.0.0 GA) — TUI front-end for the
> [SPECA](https://github.com/NyxFoundation/speca) specification-anchored
> security-audit pipeline.

```bash
npx speca-cli@latest doctor    # one-shot environment check
npm install -g speca-cli       # global install
```

`speca auth login` → `speca init` → `speca run --target 04` is the typical
first-run loop.

## Documentation

End-user documentation, command reference, and the typical workflow live on
the SPECA documentation site:

→ **[https://speca.pages.dev/](https://speca.pages.dev/)**

Quick links:

- [Installation](https://speca.pages.dev/docs/getting-started/installation) · [Quickstart](https://speca.pages.dev/docs/getting-started/quickstart)
- [Audit walkthrough](https://speca.pages.dev/docs/tutorial/audit-walkthrough)
- [Pipeline overview](https://speca.pages.dev/docs/pipeline/overview)

## MCP server configuration

Pipeline phases that use MCP servers (spec fetch, subgraph extraction,
code-scope resolution) read a `.mcp.json`, resolved in this order:

1. `SPECA_MCP_CONFIG` — environment variable pointing at an explicit config
   file. When set but unreadable, `speca run` fails instead of falling back.
2. `.mcp.json` in the directory you run `speca` from (your workspace).
3. The default bundled with the npm package
   (`vendor/speca-core/.mcp.json`), which provides the `fetch`,
   `filesystem`, and `tree_sitter` servers used by the pipeline.

When a phase declares MCP servers that none of these provide, `speca run`
prints a `[MCP] WARNING` on stderr instead of silently continuing without
them.

## Internal references

- Implementation spec: [`docs/SPECA_CLI_SPEC.md`](../docs/SPECA_CLI_SPEC.md)
- Asciinema demo recordings: [`asciinema/`](asciinema/)
- Schema sync (Pydantic → JSON Schema): [`src/lib/schemas/generated/`](src/lib/schemas/generated/)
- Tests: `npm test` (vitest); coverage: `npm run test:coverage`
- Type-check: `npm run typecheck`
- Build: `npm run build`

## License

MIT — see the project's top-level [`LICENSE`](../LICENSE).
