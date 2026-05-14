// @ts-check

// This runs in Node.js - Don't use client-side code here (browser APIs, JSX...)

/**
 * Creating a sidebar enables you to:
 - create an ordered group of docs
 - render a sidebar for each doc of that group
 - provide next/previous navigation

 The sidebars can be generated from the filesystem, or explicitly defined here.

 Create as many sidebars as you want.

 @type {import('@docusaurus/plugin-content-docs').SidebarsConfig}
 */
const sidebars = {
  tutorialSidebar: [
    'intro',
    'results-overview',
    {
      type: 'category',
      label: 'やさしいガイド',
      collapsed: false,
      items: [
        'guide/what-is-speca',
        'guide/how-it-works',
        'guide/try-it',
        'guide/web-ui',
        'guide/faq',
      ],
    },
    {
      type: 'category',
      label: '実戦チュートリアル',
      collapsed: false,
      items: ['tutorial/audit-walkthrough'],
    },
    {
      type: 'category',
      label: 'はじめに',
      collapsed: false,
      items: [
        'getting-started/installation',
        'getting-started/quickstart',
        'getting-started/web-ui-quickstart',
        'getting-started/cli-reference',
        'getting-started/config-files',
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
      label: '概念',
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
      collapsed: false,
      items: [
        'agent-design/overview',
        'agent-design/harness',
        'agent-design/prompts-and-skills',
        'agent-design/context-engineering',
      ],
    },
    {
      type: 'category',
      label: 'リファレンス',
      collapsed: false,
      items: ['references/paper-fusaka', 'references/paper-multi-impl'],
    },
    {
      type: 'category',
      label: '運用ガイド',
      collapsed: false,
      items: [
        'operations/overview',
        'operations/multi-runtime',
        'operations/web-ui-features',
        'operations/troubleshooting',
        'operations/dataset-refresh',
        'operations/release-artifacts',
        'operations/benchmark-rq1',
        'operations/benchmark-rq2a',
        'operations/benchmark-rq2b',
      ],
    },
    'project-structure',
    {
      type: 'category',
      label: '設計の裏側',
      collapsed: true,
      items: ['design-notes/why-spec-driven', 'design-notes/model-benchmark-takeaways'],
    },
    {
      type: 'category',
      label: 'コミュニティ',
      collapsed: false,
      items: ['community/thanks'],
    },
    'achievements',
  ],
};

export default sidebars;
