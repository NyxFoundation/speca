// FindingRow — one row in the findings list.
//
// On wide screens it renders as a table-row look-alike (display: grid with
// fixed column widths). On narrow screens the CSS collapses it into a
// stacked card via a media query. Both layouts share the same DOM so we
// don't need to gate behind a hook.

import { Link } from "react-router-dom";

import { OpenInVSCode } from "@/components/OpenInVSCode";
import { useT } from "@/i18n/useT";

import { parseLineStart } from "./parseLineRange";
import { SeverityChip } from "./SeverityChip";
import { VerdictChip } from "./VerdictChip";
import styles from "./FindingRow.module.css";

import type { Finding } from "./types";

interface Props {
  finding: Finding;
  runId: string;
  /**
   * Absolute path to the SPECA repo root, threaded down from the page so
   * the row can synthesise `<repo>/target_workspace/<file>` for the
   * Slice G "Open in VSCode" icon. May be `null` while the integrations
   * paths query is still in flight — the icon is omitted in that case.
   */
  repoRoot?: string | null;
}

export function FindingRow({ finding, runId, repoRoot }: Props) {
  const t = useT();
  const codeLocation =
    finding.file && finding.line_range
      ? `${finding.file}::${finding.line_range}`
      : finding.file ?? t("common.none");

  const vscodePath =
    repoRoot && finding.file
      ? `${repoRoot}/target_workspace/${finding.file}`
      : null;
  const vscodeLine = parseLineStart(finding.line_range);

  return (
    <div className={styles.row} data-property-id={finding.property_id}>
      <Link
        to={`/runs/${encodeURIComponent(runId)}/findings/${encodeURIComponent(
          finding.property_id,
        )}`}
        className={styles.rowLink}
      >
        <div className={styles.severityCell}>
          <SeverityChip severity={finding.severity} compact />
        </div>
        <div className={styles.idCell} title={finding.property_id}>
          {finding.property_id}
          {finding.target && (
            <span className={styles.target} title={finding.target}>
              {finding.target}
            </span>
          )}
        </div>
        <div className={styles.verdictCell}>
          <VerdictChip verdict={finding.verdict} />
        </div>
        <div className={styles.fileCell} title={codeLocation}>
          {codeLocation}
        </div>
        <div className={styles.phaseCell}>{finding.phase}</div>
      </Link>
      <div className={styles.rowActions}>
        {vscodePath ? (
          <OpenInVSCode
            path={vscodePath}
            line={vscodeLine ?? undefined}
            label={t("findings.list.open_in_vscode")}
            variant="icon"
          />
        ) : null}
      </div>
    </div>
  );
}
