// @ts-check

// This runs in Node.js - Don't use client-side code here (browser APIs, JSX...)

/**
 * Sidebar layout.
 *
 * Categorisation principles (changed 2026-05):
 *
 * - Avoid katakana / loanwords / unusual terms in category labels.
 *   `リファレンス` (loanword for "references") was renamed `論文` because
 *   the items underneath are literally papers. `設計の裏側` was
 *   renamed `設計ノート` for the same reason.
 * - Collapse 1-item categories into a logical neighbour (no single-row
 *   parents). The old `実戦チュートリアル` (one walkthrough) moved into
 *   the setup flow.
 * - Group everyday usage guides (CLI ref, Web UI tour, multi-runtime,
 *   troubleshooting at-a-glance) into a single `使い方ガイド` block so
 *   users do not bounce between "Getting started", "Operations", and
 *   the generic guide each time.
 *
 * @type {import('@docusaurus/plugin-content-docs').SidebarsConfig}
 */
const sidebars = {
  tutorialSidebar: [
    'intro',
    'results-overview',
    {
      type: 'category',
      label: '入門',
      collapsed: false,
      items: [
        'guide/what-is-speca',
        'guide/how-it-works',
        'guide/faq',
      ],
    },
    {
      type: 'category',
      label: 'セットアップ & 初回実行',
      collapsed: false,
      items: [
        'getting-started/installation',
        'getting-started/config-files',
        'getting-started/quickstart',
        'getting-started/web-ui-quickstart',
        'guide/try-it',
        'tutorial/audit-walkthrough',
      ],
    },
    {
      type: 'category',
      label: '使い方ガイド',
      collapsed: false,
      items: [
        'guide/web-ui',
        'getting-started/cli-reference',
        'operations/multi-runtime',
        'operations/web-ui-features',
      ],
    },
    {
      type: 'category',
      label: 'パイプライン',
      collapsed: false,
      items: [
        'pipeline/overview',
        'pipeline/01a-spec-discovery',
        'pipeline/01b-subgraph-extraction',
        'pipeline/01e-property-generation',
        'pipeline/02c-code-resolution',
        'pipeline/audit-map',
        'pipeline/review',
      ],
    },
    {
      type: 'category',
      label: '仕組み',
      collapsed: true,
      items: [
        'concepts/spec-driven',
        'concepts/proof-attempt',
        'concepts/gate-review',
        'concepts/bug-bounty-scope',
        'concepts/worked-example',
      ],
    },
    {
      type: 'category',
      label: 'エージェント設計',
      collapsed: true,
      items: [
        'agent-design/overview',
        'agent-design/harness',
        'agent-design/prompts-and-skills',
        'agent-design/context-engineering',
      ],
    },
    {
      type: 'category',
      label: '運用',
      collapsed: true,
      items: [
        'operations/overview',
        'operations/troubleshooting',
        'operations/dataset-refresh',
        'operations/release-artifacts',
        'operations/benchmark-rq1',
        'operations/benchmark-rq2a',
        'operations/benchmark-rq2b',
      ],
    },
    {
      type: 'category',
      label: '論文',
      collapsed: true,
      items: ['references/paper-fusaka', 'references/paper-multi-impl'],
    },
    {
      type: 'category',
      label: '設計ノート',
      collapsed: true,
      items: ['design-notes/why-spec-driven', 'design-notes/model-benchmark-takeaways'],
    },
    'project-structure',
    'community/thanks',
    'achievements',
  ],
};

export default sidebars;
