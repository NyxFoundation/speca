// SettingsPage — `/settings`.
//
// v0 surface (per UI_DESIGN.md Slice G):
//   1. Auth status   — read-only summary of the active login method.
//   2. Integrations  — `code` / `gh` presence + auth probe.
//   3. Maintenance   — three <OpenInVSCode> launchers for the absolute
//      paths the backend surfaces via /api/integrations/paths.
//
// Slice S1 adds a fourth section, appended below the v0 trio:
//   4. Fork target_repo to GitHub — `gh repo fork` wrapper gated by a
//      ConfirmDialog. Disabled while `gh` is missing / unauthenticated.
//
// The v0 sections remain read-only by intent; writes (logout, key rotation,
// repo picker) land in v1. Every action that could fail is gated on the
// data being loaded — we render a thin spinner placeholder if the
// integrations paths query is still in flight rather than mounting a
// disabled <OpenInVSCode> with an empty `path`.

import { useMemo, useState, type ReactElement } from "react";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { OpenInVSCode } from "@/components/OpenInVSCode";
import { useAuthStatus } from "@/features/auth/useAuth";
import { useFork } from "@/features/integrations/useFork";
import {
  useIntegrationsPaths,
  useIntegrationsStatus,
} from "@/features/integrations/useIntegrationsStatus";
import { useT } from "@/i18n/useT";

import { RuntimeSection } from "./RuntimeSection";
import styles from "./SettingsPage.module.css";

// Same regex the B4 ForkRequest validator uses. Keeping it inline (rather
// than re-exporting from the schema layer) means a backend change requires
// a deliberate edit here too — the parity is intentional.
const TARGET_REPO_RE = /^[A-Za-z0-9._-]+\/[A-Za-z0-9._-]+$/;

function StatusDot({ ok }: { ok: boolean | null }): ReactElement {
  const cls =
    ok === true
      ? styles.dotOk
      : ok === false
        ? styles.dotMissing
        : styles.dotUnknown;
  return <span className={`${styles.dot} ${cls}`} aria-hidden="true" />;
}

function AuthSection(): ReactElement {
  const t = useT();
  const { data, isPending, isError } = useAuthStatus();

  if (isPending) {
    return <p className={styles.muted}>{t("settings.auth.loading")}</p>;
  }
  if (isError || !data) {
    return <p className={styles.muted}>{t("settings.auth.load_failed")}</p>;
  }

  const methodLabel =
    data.method === "oauth"
      ? t("settings.auth.method_oauth")
      : data.method === "api_key"
        ? t("settings.auth.method_api_key")
        : t("settings.auth.method_none");

  return (
    <dl className={styles.kv} data-testid="settings-auth-block">
      <div className={styles.kvRow}>
        <dt>{t("settings.auth.login_state")}</dt>
        <dd>
          <StatusDot ok={data.logged_in} />{" "}
          {data.logged_in
            ? t("settings.auth.logged_in")
            : t("settings.auth.not_logged_in")}
        </dd>
      </div>
      <div className={styles.kvRow}>
        <dt>{t("settings.auth.method")}</dt>
        <dd>{methodLabel}</dd>
      </div>
      {data.identity ? (
        <div className={styles.kvRow}>
          <dt>{t("settings.auth.identity")}</dt>
          <dd>
            <code>{data.identity}</code>
          </dd>
        </div>
      ) : null}
    </dl>
  );
}

function IntegrationsSection(): ReactElement {
  const t = useT();
  const { data, isPending, isError } = useIntegrationsStatus();

  if (isPending) {
    return <p className={styles.muted}>{t("settings.integrations.loading")}</p>;
  }
  if (isError || !data) {
    return (
      <p className={styles.muted}>{t("settings.integrations.load_failed")}</p>
    );
  }

  return (
    <dl className={styles.kv} data-testid="settings-integrations-block">
      <div className={styles.kvRow}>
        <dt>{t("settings.integrations.vscode_cli")}</dt>
        <dd>
          <StatusDot ok={data.code.installed} />{" "}
          {data.code.installed
            ? data.code.version ?? t("settings.integrations.installed")
            : t("settings.integrations.not_found")}
        </dd>
      </div>
      <div className={styles.kvRow}>
        <dt>{t("settings.integrations.github_cli")}</dt>
        <dd>
          <StatusDot ok={data.gh.installed} />{" "}
          {data.gh.installed
            ? data.gh.version ?? t("settings.integrations.installed")
            : t("settings.integrations.not_found")}
        </dd>
      </div>
      {data.gh.installed ? (
        <div className={styles.kvRow}>
          <dt>{t("settings.integrations.gh_auth")}</dt>
          <dd>
            <StatusDot ok={data.gh.authed} />{" "}
            {data.gh.authed === true
              ? t("settings.auth.logged_in")
              : data.gh.authed === false
                ? t("settings.auth.not_logged_in")
                : t("settings.integrations.unknown")}
          </dd>
        </div>
      ) : null}
    </dl>
  );
}

function MaintenanceSection(): ReactElement {
  const t = useT();
  const { data, isPending, isError } = useIntegrationsPaths();

  if (isPending) {
    return <p className={styles.muted}>{t("settings.maintenance.loading")}</p>;
  }
  if (isError || !data) {
    return (
      <p className={styles.muted}>{t("settings.maintenance.load_failed")}</p>
    );
  }

  return (
    <div className={styles.actions} data-testid="settings-maintenance-block">
      <OpenInVSCode
        path={data.speca_dir}
        label={t("settings.maintenance.open_speca_dir")}
        variant="button"
      />
      <OpenInVSCode
        path={data.repo_root}
        label={t("settings.maintenance.open_repo")}
        variant="button"
      />
      <OpenInVSCode
        path={data.claude_dir}
        label={t("settings.maintenance.open_claude_dir")}
        variant="button"
      />
    </div>
  );
}

function ForkSection(): ReactElement {
  const t = useT();
  const status = useIntegrationsStatus();
  const forkMutation = useFork();

  const [targetRepo, setTargetRepo] = useState("");
  const [intoOwner, setIntoOwner] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);

  // ``gh`` is "ready" only when both probes pass. We don't gate on the
  // status query being loaded — disabling the inputs while we're still
  // pending would be a worse UX than a momentarily-clickable button that
  // gets re-disabled once the probe finishes. The backend also gates this
  // (returns 503 ``gh_cli_not_found``) so a transient race window is safe.
  const ghReady = Boolean(status.data?.gh.installed && status.data?.gh.authed);

  const targetRepoValid = useMemo(
    () => TARGET_REPO_RE.test(targetRepo.trim()),
    [targetRepo],
  );

  const submitDisabled = !ghReady || !targetRepoValid || forkMutation.isPending;

  const handleSubmit = (): void => {
    if (submitDisabled) return;
    setDialogOpen(true);
  };

  const handleConfirm = (): void => {
    setDialogOpen(false);
    const trimmedOwner = intoOwner.trim();
    forkMutation.mutate({
      target_repo: targetRepo.trim(),
      into_owner: trimmedOwner === "" ? undefined : trimmedOwner,
      confirmed: true,
    });
  };

  const buttonTooltip = !ghReady
    ? t("settings.fork.gh_required_tooltip")
    : undefined;

  return (
    <>
      <div className={styles.forkForm} data-testid="settings-fork-block">
        <label className={styles.field}>
          <input
            type="text"
            className={styles.input}
            placeholder={t("settings.fork.target_repo_placeholder")}
            value={targetRepo}
            onChange={(e) => setTargetRepo(e.target.value)}
            aria-invalid={targetRepo.length > 0 && !targetRepoValid}
            aria-label={t("settings.fork.target_repo_placeholder")}
            disabled={!ghReady}
            data-testid="settings-fork-target-repo"
          />
        </label>
        <label className={styles.field}>
          <input
            type="text"
            className={styles.input}
            placeholder={t("settings.fork.into_owner_placeholder")}
            value={intoOwner}
            onChange={(e) => setIntoOwner(e.target.value)}
            aria-label={t("settings.fork.into_owner_placeholder")}
            disabled={!ghReady}
            data-testid="settings-fork-into-owner"
          />
        </label>
        <button
          type="button"
          className={styles.submit}
          onClick={handleSubmit}
          disabled={submitDisabled}
          title={buttonTooltip}
          data-testid="settings-fork-submit"
        >
          {t("settings.fork.submit")}
        </button>
        {forkMutation.isSuccess && forkMutation.data ? (
          <div className={styles.success} data-testid="settings-fork-success">
            {t("settings.fork.success")}{" "}
            <a
              href={forkMutation.data.fork_url}
              target="_blank"
              rel="noreferrer"
            >
              {forkMutation.data.forked_repo}
            </a>
          </div>
        ) : null}
        {forkMutation.isError && forkMutation.errorMessage ? (
          <div className={styles.error} data-testid="settings-fork-error">
            {forkMutation.errorMessage}
          </div>
        ) : null}
      </div>
      <ConfirmDialog
        open={dialogOpen}
        title={t("settings.fork.confirm.title", { repo: targetRepo.trim() })}
        description={t("settings.fork.confirm.description")}
        destructive={false}
        onConfirm={handleConfirm}
        onCancel={() => setDialogOpen(false)}
      />
    </>
  );
}

export function SettingsPage(): ReactElement {
  const t = useT();
  return (
    <section className={styles.page} data-testid="settings-page">
      <header className={styles.header}>
        <h1 className={styles.title}>{t("settings.page.title")}</h1>
        <p className={styles.subtitle}>{t("settings.page.subtitle")}</p>
      </header>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>{t("settings.page.section_auth")}</h2>
        <AuthSection />
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>
          {t("settings.page.section_runtime")}
        </h2>
        <p className={styles.sectionHint}>
          {t("settings.page.runtime_hint")}
        </p>
        <RuntimeSection />
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>
          {t("settings.page.section_integrations")}
        </h2>
        <IntegrationsSection />
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>
          {t("settings.page.section_maintenance")}
        </h2>
        <p className={styles.sectionHint}>{t("settings.page.maintenance_hint")}</p>
        <MaintenanceSection />
      </section>

      <ForkSectionWrapper />
    </section>
  );
}

// Wrapper that owns the section heading + description so ForkSection can
// stay focused on form state. Inlined here because no other page needs
// the section chrome.
function ForkSectionWrapper(): ReactElement {
  const t = useT();
  return (
    <section className={styles.section}>
      <h2 className={styles.sectionTitle}>{t("settings.fork.title")}</h2>
      <p className={styles.sectionHint}>{t("settings.fork.description")}</p>
      <ForkSection />
    </section>
  );
}

export default SettingsPage;
