// FilterBar — severity chips + verdict chips + phase toggle.
//
// State lives in the URL via `useSearchParams` so a finding list link can
// be bookmarked / shared with filters intact. The page itself reads the
// same searchParams to drive the query, so this component never has to
// "lift state up" — it just edits the URL.

import { useSearchParams } from "react-router-dom";

import { useT } from "@/i18n/useT";

import styles from "./FilterBar.module.css";

import {
  KNOWN_VERDICTS,
  PHASES,
  SEVERITY_LEVELS,
  type Phase,
  type Severity,
} from "./types";

interface FilterBarProps {
  /** Distinct client/target names from `meta.targets`. When empty (a
   * single-target run) the client filter is hidden entirely. */
  targets?: string[];
}

export function FilterBar({ targets = [] }: FilterBarProps) {
  const t = useT();
  const [searchParams, setSearchParams] = useSearchParams();
  const currentSeverity = searchParams.get("severity") as Severity | null;
  const currentVerdict = searchParams.get("verdict");
  const currentPhase = searchParams.get("phase") as Phase | null;
  const currentTarget = searchParams.get("target");

  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(searchParams);
    if (value === null || value === "") {
      next.delete(key);
    } else {
      next.set(key, value);
    }
    setSearchParams(next, { replace: true });
  };

  return (
    <section className={styles.bar} aria-label={t("findings.filter.bar_aria")}>
      {targets.length > 0 && (
        <div className={styles.group}>
          <span className={styles.groupLabel}>
            {t("findings.filter.client_label")}
          </span>
          <select
            className={styles.select}
            aria-label={t("findings.filter.client_label")}
            value={currentTarget ?? ""}
            onChange={(e) => setParam("target", e.target.value || null)}
          >
            <option value="">{t("findings.filter.all_clients")}</option>
            {targets.map((tgt) => (
              <option key={tgt} value={tgt}>
                {tgt}
              </option>
            ))}
          </select>
        </div>
      )}

      <div className={styles.group}>
        <span className={styles.groupLabel}>
          {t("findings.filter.severity_label")}
        </span>
        <button
          type="button"
          className={`${styles.chip} ${currentSeverity === null ? styles.chipActive : ""}`}
          onClick={() => setParam("severity", null)}
        >
          {t("findings.filter.all")}
        </button>
        {SEVERITY_LEVELS.map((sev) => (
          <button
            key={sev}
            type="button"
            className={`${styles.chip} ${currentSeverity === sev ? styles.chipActive : ""}`}
            onClick={() => setParam("severity", sev)}
          >
            {t(`findings.severity.${sev}`)}
          </button>
        ))}
      </div>

      <div className={styles.group}>
        <span className={styles.groupLabel}>
          {t("findings.filter.verdict_label")}
        </span>
        <button
          type="button"
          className={`${styles.chip} ${currentVerdict === null ? styles.chipActive : ""}`}
          onClick={() => setParam("verdict", null)}
        >
          {t("findings.filter.all")}
        </button>
        {KNOWN_VERDICTS.map((v) => (
          <button
            key={v}
            type="button"
            className={`${styles.chip} ${currentVerdict === v ? styles.chipActive : ""}`}
            onClick={() => setParam("verdict", v)}
            title={v}
          >
            {t(`findings.verdict.${v}`)}
          </button>
        ))}
      </div>

      <div className={styles.group}>
        <span className={styles.groupLabel}>
          {t("findings.filter.phase_label")}
        </span>
        <button
          type="button"
          className={`${styles.chip} ${currentPhase === null ? styles.chipActive : ""}`}
          onClick={() => setParam("phase", null)}
        >
          {t("findings.filter.all")}
        </button>
        {PHASES.map((p) => (
          <button
            key={p}
            type="button"
            className={`${styles.chip} ${currentPhase === p ? styles.chipActive : ""}`}
            onClick={() => setParam("phase", p)}
          >
            {t("findings.filter.phase_value", { phase: p })}
          </button>
        ))}
      </div>
    </section>
  );
}
