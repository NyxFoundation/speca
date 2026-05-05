/**
 * Finding detail view / code peek for the finding browser (M4).
 */
import { Box, Text } from "ink";
import type { Finding } from "../lib/findings.js";

interface FindingDetailProps {
  finding: Finding;
}

export function FindingDetail({ finding }: FindingDetailProps) {
  return (
    <Box flexDirection="column" paddingX={1}>
      <Box gap={1} marginBottom={1}>
        <Text bold>Property:</Text>
        <Text>{finding.propertyId}</Text>
        {finding.checkId && finding.checkId !== finding.propertyId && (
          <>
            <Text dimColor>|</Text>
            <Text dimColor>Check: {finding.checkId}</Text>
          </>
        )}
      </Box>

      <Box gap={1}>
        <Text bold>Classification:</Text>
        <Text>{finding.classification || "-"}</Text>
      </Box>

      <Box gap={1}>
        <Text bold>Severity:</Text>
        <Text color={finding.severity === "Critical" ? "red" : finding.severity === "High" ? "redBright" : "white"}>
          {finding.severity || "-"}
        </Text>
      </Box>

      <Box gap={1}>
        <Text bold>Verdict:</Text>
        <Text color={finding.verdict === "Confirmed" ? "red" : finding.verdict === "Disputed" ? "green" : "white"}>
          {finding.verdict || "-"}
        </Text>
      </Box>

      {finding.summary && (
        <Box flexDirection="column" marginTop={1}>
          <Text bold underline>Summary</Text>
          <Text>{finding.summary}</Text>
        </Box>
      )}

      {finding.reviewerNotes && (
        <Box flexDirection="column" marginTop={1}>
          <Text bold underline>Reviewer Notes</Text>
          <Text>{finding.reviewerNotes}</Text>
        </Box>
      )}

      {finding.finalRecommendation && (
        <Box flexDirection="column" marginTop={1}>
          <Text bold underline>Recommendation</Text>
          <Text>{finding.finalRecommendation}</Text>
        </Box>
      )}

      {finding.codePath && (
        <Box flexDirection="column" marginTop={1}>
          <Text bold underline>Code Location</Text>
          <Text color="cyan">{finding.codePath}</Text>
        </Box>
      )}

      {finding.codeSnippet && (
        <Box flexDirection="column" marginTop={1} borderStyle="single" borderColor="gray" paddingX={1}>
          <Text bold dimColor>Code / Proof Trace</Text>
          <Text>{finding.codeSnippet}</Text>
        </Box>
      )}

      <Box marginTop={1}>
        <Text dimColor>Source: {finding.sourceFile} | [Esc] back to list | [c] copy ID</Text>
      </Box>
    </Box>
  );
}
