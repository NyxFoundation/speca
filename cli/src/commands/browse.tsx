/**
 * `speca browse` — interactive finding browser (M4).
 *
 * Loads Phase 04 (or Phase 03) PARTIAL_*.json files and presents a
 * severity-coloured table with filter DSL and code peek.
 *
 * Spec ref: Issue #3 M4, SPECA_CLI_SPEC §8.4.
 */
import { Box, Text, useApp, useInput } from "ink";
import { useEffect, useState } from "react";
import { FindingDetail } from "../components/FindingDetail.js";
import { FindingTable } from "../components/FindingTable.js";
import { Layout } from "../components/Layout.js";
import {
  applyFilter,
  loadFindings,
  parseFilter,
  sortFindings,
  type Finding,
} from "../lib/findings.js";

export interface BrowseCommandProps {
  cwd?: string;
  outputsDir?: string;
  /** Initial filter query */
  filterQuery?: string;
}

type View = "table" | "detail" | "filter";

export function BrowseCommand(props: BrowseCommandProps) {
  const { exit } = useApp();
  const [allFindings, setAllFindings] = useState<Finding[]>([]);
  const [filtered, setFiltered] = useState<Finding[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [view, setView] = useState<View>("table");
  const [filterQuery, setFilterQuery] = useState(props.filterQuery ?? "");
  const [filterInput, setFilterInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load findings on mount
  useEffect(() => {
    const outputsDir = props.outputsDir ?? (props.cwd ? `${props.cwd}/outputs` : `${process.cwd()}/outputs`);
    loadFindings(outputsDir)
      .then((findings) => {
        const sorted = sortFindings(findings);
        setAllFindings(sorted);
        if (filterQuery) {
          setFiltered(applyFilter(sorted, parseFilter(filterQuery)));
        } else {
          setFiltered(sorted);
        }
        setLoading(false);
      })
      .catch((err: Error) => {
        setError(err.message);
        setLoading(false);
      });
  }, [props.outputsDir, props.cwd, filterQuery]);

  // Keyboard input
  useInput((input, key) => {
    if (view === "filter") {
      if (key.return) {
        // Apply filter
        setFilterQuery(filterInput);
        const f = applyFilter(allFindings, parseFilter(filterInput));
        setFiltered(f);
        setSelectedIndex(0);
        setView("table");
      } else if (key.escape) {
        setView("table");
      } else if (key.backspace || key.delete) {
        setFilterInput((prev) => prev.slice(0, -1));
      } else if (input && !key.ctrl && !key.meta) {
        setFilterInput((prev) => prev + input);
      }
      return;
    }

    if (view === "detail") {
      if (key.escape || input === "b") {
        setView("table");
      }
      return;
    }

    // Table view
    if (input === "q" || (key.ctrl && input === "c")) {
      exit();
    } else if (key.upArrow || input === "k") {
      setSelectedIndex((prev) => Math.max(0, prev - 1));
    } else if (key.downArrow || input === "j") {
      setSelectedIndex((prev) => Math.min(filtered.length - 1, prev + 1));
    } else if (key.return) {
      if (filtered.length > 0) setView("detail");
    } else if (input === "/") {
      setFilterInput(filterQuery);
      setView("filter");
    } else if (input === "c" && filtered[selectedIndex]) {
      // No-op in terminal (clipboard requires external tool)
    }
  });

  if (loading) {
    return (
      <Layout title="SPECA Finding Browser">
        <Text>Loading findings...</Text>
      </Layout>
    );
  }

  if (error) {
    return (
      <Layout title="SPECA Finding Browser">
        <Text color="red">Error: {error}</Text>
      </Layout>
    );
  }

  const statusText = filterQuery
    ? `Filter: "${filterQuery}" | ${filtered.length}/${allFindings.length} findings`
    : `${allFindings.length} findings`;

  if (view === "detail" && filtered[selectedIndex]) {
    return (
      <Layout title="SPECA Finding Browser" status={statusText}>
        <FindingDetail finding={filtered[selectedIndex]!} />
      </Layout>
    );
  }

  if (view === "filter") {
    return (
      <Layout title="SPECA Finding Browser" status="Filter mode">
        <Box flexDirection="column">
          <Text>
            Filter: <Text color="cyan">{filterInput}</Text>
            <Text dimColor>|</Text>
          </Text>
          <Text dimColor>
            Syntax: severity:High verdict:Confirmed prop:FN-001 free text
          </Text>
          <Text dimColor>[Enter] apply | [Esc] cancel</Text>
        </Box>
      </Layout>
    );
  }

  return (
    <Layout title="SPECA Finding Browser" status={statusText}>
      <FindingTable findings={filtered} selectedIndex={selectedIndex} />
    </Layout>
  );
}
