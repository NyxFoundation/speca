/**
 * FindingDetail — render the selected finding's full record (verdict,
 * proof trace, attack scenario, reviewer notes, code path).
 */
import { Box, Text } from "ink";

import type { Finding } from "../lib/findings/types.js";

interface FindingDetailProps {
  finding: Finding | undefined;
  expanded: boolean;
}

export function FindingDetail({ finding, expanded }: FindingDetailProps) {
  if (!finding) {
    return (
      <Box>
        <Text dimColor>(no selection)</Text>
      </Box>
    );
  }
  const sev = finding.severity || finding.rawSeverity || "—";
  return (
    <Box flexDirection="column">
      <Box>
        <Text bold>Property: </Text>
        <Text>{finding.propertyId}</Text>
        <Text dimColor>{`  (severity: ${sev})`}</Text>
      </Box>
      <Box>
        <Text bold>Verdict:  </Text>
        <Text color="cyan">{finding.verdict || "—"}</Text>
      </Box>
      {finding.classification ? (
        <Box>
          <Text bold>Classification: </Text>
          <Text>{finding.classification}</Text>
        </Box>
      ) : null}
      {finding.specReference ? (
        <Box>
          <Text bold>Spec ref: </Text>
          <Text>{finding.specReference}</Text>
        </Box>
      ) : null}
      <Box marginTop={1} flexDirection="column">
        <Text bold underline>Reviewer notes</Text>
        <Wrapped text={finding.reviewerNotes || "(none)"} expanded={expanded} maxLines={expanded ? 20 : 4} />
      </Box>
      {finding.proofTrace ? (
        <Box marginTop={1} flexDirection="column">
          <Text bold underline>Proof trace</Text>
          <Wrapped text={finding.proofTrace} expanded={expanded} maxLines={expanded ? 20 : 4} />
        </Box>
      ) : null}
      {finding.attackScenario ? (
        <Box marginTop={1} flexDirection="column">
          <Text bold underline>Attack scenario</Text>
          <Wrapped text={finding.attackScenario} expanded={expanded} maxLines={expanded ? 20 : 4} />
        </Box>
      ) : null}
      {finding.primaryLocation && finding.primaryLocation.file ? (
        <Box marginTop={1} flexDirection="column">
          <Text bold underline>Code path</Text>
          <Text>
            {finding.primaryLocation.file}
            {finding.primaryLocation.symbol ? `::${finding.primaryLocation.symbol}` : ""}
            {finding.primaryLocation.startLine ? `:${finding.primaryLocation.startLine}` : ""}
            {finding.primaryLocation.endLine && finding.primaryLocation.endLine !== finding.primaryLocation.startLine
              ? `-${finding.primaryLocation.endLine}`
              : ""}
          </Text>
        </Box>
      ) : null}
    </Box>
  );
}

interface WrappedProps {
  text: string;
  expanded: boolean;
  maxLines: number;
}

function Wrapped({ text, expanded, maxLines }: WrappedProps) {
  const lines = text.split(/\r?\n/);
  const shown = lines.slice(0, maxLines);
  const truncated = lines.length > shown.length;
  return (
    <Box flexDirection="column">
      {shown.map((line, idx) => (
        <Text key={idx}>{line}</Text>
      ))}
      {truncated && !expanded ? <Text dimColor>(press Enter to expand…)</Text> : null}
      {truncated && expanded ? <Text dimColor>{`(+${lines.length - shown.length} more lines)`}</Text> : null}
    </Box>
  );
}
