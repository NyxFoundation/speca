// FindingsListPage — `/runs/<runId>/findings`.
//
// Three sections, top to bottom:
//   1. Banner explaining `data_source: current_outputs` (v0 caveat)
//   2. FilterBar — severity/verdict/phase chips, URL-synced
//   3. Sortable table — five columns, click-sortable headers
//
// Sort is local because the server returns a small dataset (<1k rows in
// the litecoin sample). The default is severity-ascending; clicking the
// same header toggles direction. We deliberately do NOT persist the sort
// to the URL — it's a workspace concern, not a shareable filter.

import { useMemo, useState } from "react";

// Cap the initial DOM render so a 1k-finding run doesn't ship a 46k px
// scroll viewport to the browser. The "Show all" button reveals the rest
// without virtualisation — proper windowing is a v2 perf task.
const INITIAL_PAGE_SIZE = 100;
import { useParams, useSearchParams } from "react-router-dom";

import { useIntegrationsPaths } from "@/features/integrations/useIntegrationsStatus";
import { useT } from "@/i18n/useT";

import { findingsToMarkdown } from "./exportMarkdown";
import { FilterBar } from "./FilterBar";
import { FilterInput } from "./FilterInput";
import { FindingRow } from "./FindingRow";
import { isEmptyFilter, matchFilter, parseFilterDsl } from "./filterDsl";
import { useDownloadMarkdown } from "./useDownloadMarkdown";
import { useFindings } from "./useFindings";
import styles from "./FindingsListPage.module.css";

import {
  SEVERITY_RANK,
  type Finding,
  type FindingQuery,
  type Phase,
  type Severity,
} from "./types";

type SortKey = "severity" | "property_id" | "verdict" | "file" | "phase";
type SortDir = "asc" | "desc";

interface SortState {
  key: SortKey;
  dir: SortDir;
}

const HEADERS: { key: SortKey; i18nKey: string; className: string }[] = [
  { key: "severity", i18nKey: "findings.list.col_severity", className: "severityCol" },
  { key: "property_id", i18nKey: "findings.list.col_property_id", className: "idCol" },
  { key: "verdict", i18nKey: "findings.list.col_verdict", className: "verdictCol" },
  { key: "file", i18nKey: "findings.list.col_file", className: "fileCol" },
  { key: "phase", i18nKey: "findings.list.col_phase", className: "phaseCol" },
];

function compare(a: Finding, b: Finding, key: SortKey, dir: SortDir): number {
  let cmp = 0;
  switch (key) {
    case "severity":
      cmp = SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity];
      break;
    case "property_id":
      cmp = a.property_id.localeCompare(b.property_id);
      break;
    case "verdict":
      cmp = (a.verdict ?? "").localeCompare(b.verdict ?? "");
      break;
    case "file":
      cmp = (a.file ?? "").localeCompare(b.file ?? "");
      break;
    case "phase":
      cmp = a.phase.localeCompare(b.phase);
      break;
  }
  // Stable tie-break by property_id so two findings with the same severity
  // don't bounce around as the user toggles other columns.
  if (cmp === 0 && key !== "property_id") {
    cmp = a.property_id.localeCompare(b.property_id);
  }
  // Final tie-break by target — property ids repeat across clients in a
  // multi-client audit, so without this the relative order of the same
  // property's per-client rows would be unstable.
  if (cmp === 0) {
    cmp = (a.target ?? "").localeCompare(b.target ?? "");
  }
  return dir === "asc" ? cmp : -cmp;
}

export function FindingsListPage() {
  const t = useT();
  const { runId } = useParams<{ runId: string }>();
  const [searchParams] = useSearchParams();
  const [sort, setSort] = useState<SortState>({ key: "severity", dir: "asc" });

  const query: FindingQuery = useMemo(() => {
    const sev = searchParams.get("severity");
    const verd = searchParams.get("verdict");
    const ph = searchParams.get("phase");
    const tgt = searchParams.get("target");
    return {
      severity: (sev ?? undefined) as Severity | undefined,
      verdict: verd ?? undefined,
      phase: (ph ?? undefined) as Phase | undefined,
      target: tgt ?? undefined,
    };
  }, [searchParams]);

  const { data, error, isLoading } = useFindings(runId, query);
  // Slice G — threaded down into FindingRow so each row can render an
  // "Open in VSCode" icon pointing at <repo>/target_workspace/<file>.
  const { data: paths } = useIntegrationsPaths();

  // CLI spec §5.4.1 filter DSL — parsed once per `q=` change. The chip
  // bar above still filters server-side; the DSL is layered client-side
  // and AND-combined with whatever the server returned.
  //
  // CLI spec §3.5 `speca browse [glob]` — accept ``?glob=<pattern>`` as
  // a convenience that maps to ``?q=path:<glob>`` so deep-links from a
  // CLI session land in the right place without the user knowing the
  // DSL grammar.
  const dslQuery = useMemo(() => {
    const q = searchParams.get("q") ?? "";
    const glob = searchParams.get("glob");
    if (!glob) return q;
    const fragment = `path:${glob}`;
    return q.includes(fragment) ? q : (q ? `${q} ${fragment}` : fragment);
  }, [searchParams]);
  const parsedDsl = useMemo(() => parseFilterDsl(dslQuery), [dslQuery]);

  const sortedFindings = useMemo(() => {
    if (!data) return [];
    let rows = data.data;
    if (!isEmptyFilter(parsedDsl)) {
      rows = rows.filter((f) => matchFilter(f, parsedDsl));
    }
    const copy = [...rows];
    copy.sort((a, b) => compare(a, b, sort.key, sort.dir));
    return copy;
  }, [data, sort, parsedDsl]);

  const [showAll, setShowAll] = useState(false);
  const visibleFindings = useMemo(
    () =>
      showAll || sortedFindings.length <= INITIAL_PAGE_SIZE
        ? sortedFindings
        : sortedFindings.slice(0, INITIAL_PAGE_SIZE),
    [sortedFindings, showAll],
  );
  const hiddenCount = sortedFindings.length - visibleFindings.length;

  const handleSort = (key: SortKey) => {
    setSort((prev) =>
      prev.key === key
        ? { key, dir: prev.dir === "asc" ? "desc" : "asc" }
        : { key, dir: "asc" },
    );
  };

  // CLI spec §3.1 step 7 — Markdown export of the currently visible
  // (filter+sort applied) findings. We deliberately pass `sortedFindings`
  // and NOT `visibleFindings`: the "Show all" pagination cap is a DOM
  // perf concern, not a user-facing filter, so the export should always
  // reflect the full filtered set.
  const downloadMarkdown = useDownloadMarkdown();
  const handleExport = () => {
    if (!data || sortedFindings.length === 0) return;
    const text = findingsToMarkdown({
      runId: runId ?? "unknown",
      findings: sortedFindings,
      meta: { count: data.meta.count },
    });
    const filename = `${runId ?? "speca"}-findings.md`;
    downloadMarkdown(text, filename);
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.headerText}>
          <h2 className={styles.title}>{t("findings.list.title")}</h2>
          <p className={styles.runLabel}>
            {t("findings.list.run_label")}{" "}
            <code>{runId ?? t("common.none")}</code>
          </p>
        </div>
        <button
          type="button"
          className={styles.exportButton}
          onClick={handleExport}
          disabled={!data || sortedFindings.length === 0}
          data-testid="findings-export"
          title={t("findings.list.export_filename_hint")}
        >
          {t("findings.list.export_markdown")}
        </button>
      </header>

      {data && (
        <div className={styles.banner} role="status">
          <strong
            dangerouslySetInnerHTML={{
              __html: t("findings.list.banner_strong"),
            }}
          />{" "}
          {t("findings.list.banner_text", { count: data.meta.count })}
        </div>
      )}

      <FilterInput parsed={parsedDsl} />
      <FilterBar targets={data?.meta.targets ?? []} />

      {isLoading && (
        <div className={styles.state}>{t("findings.list.loading")}</div>
      )}

      {error && (
        <div className={styles.error}>
          {t("findings.list.load_failed", { error: error.message })}
        </div>
      )}

      {!isLoading && !error && sortedFindings.length === 0 && (
        <div className={styles.empty}>
          {t("findings.list.empty_line1")}{" "}
          <span
            dangerouslySetInnerHTML={{
              __html: t("findings.list.empty_line2"),
            }}
          />
        </div>
      )}

      {sortedFindings.length > 0 && (
        <div
          className={styles.table}
          role="table"
          aria-label={t("findings.list.table_aria")}
        >
          <div className={styles.thead} role="row">
            {HEADERS.map((h) => (
              <button
                key={h.key}
                type="button"
                role="columnheader"
                aria-sort={
                  sort.key === h.key
                    ? sort.dir === "asc"
                      ? "ascending"
                      : "descending"
                    : "none"
                }
                onClick={() => handleSort(h.key)}
                className={`${styles.th} ${styles[h.className]}`}
              >
                {t(h.i18nKey)}
                {sort.key === h.key && (
                  <span className={styles.sortArrow}>
                    {sort.dir === "asc" ? "▲" : "▼"}
                  </span>
                )}
              </button>
            ))}
          </div>
          <div className={styles.tbody}>
            {visibleFindings.map((f) => (
              <FindingRow
                // Property ids repeat across clients in a multi-client
                // audit, so the key must include the target.
                key={`${f.target ?? ""}::${f.property_id}`}
                finding={f}
                runId={runId ?? ""}
                repoRoot={paths?.repo_root ?? null}
              />
            ))}
          </div>
          {hiddenCount > 0 && (
            <div className={styles.loadMore}>
              <p className={styles.loadMoreHint}>
                {t("findings.list.showing_n_of_m", {
                  shown: visibleFindings.length,
                  total: sortedFindings.length,
                })}
              </p>
              <button
                type="button"
                className={styles.loadMoreButton}
                onClick={() => setShowAll(true)}
              >
                {t("findings.list.show_all", { n: hiddenCount })}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default FindingsListPage;
