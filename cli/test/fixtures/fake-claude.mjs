#!/usr/bin/env node
/**
 * Fake `claude` CLI used by ask.spawn.test.ts.
 *
 * Reads the prompt from stdin and emits a deterministic stream-json sequence
 * back on stdout, then exits 0. The shape mirrors the real
 * `claude --output-format stream-json` events well enough to exercise our
 * line-buffered parser:
 *
 *   {type:"system",   subtype:"init", session_id:"<uuid>"}
 *   {type:"assistant",message:{content:[{type:"text", text:"<echo of prompt>"}]}, session_id:"<uuid>"}
 *   {type:"result",   subtype:"success", session_id:"<uuid>"}
 *
 * Recognises a `--resume <id>` argv pair and re-emits that id verbatim so
 * tests can verify session continuity.
 */
import { stdin, stdout } from "node:process";

function findResumeId(argv) {
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--resume" && i + 1 < argv.length) {
      return argv[i + 1];
    }
  }
  return null;
}

const sessionId = findResumeId(process.argv) || "fake-session-uuid-0001";

let prompt = "";
stdin.setEncoding("utf8");
stdin.on("data", (c) => {
  prompt += c;
});
stdin.on("end", () => {
  const events = [
    { type: "system", subtype: "init", session_id: sessionId },
    {
      type: "assistant",
      session_id: sessionId,
      message: {
        content: [
          { type: "text", text: `echo: ${prompt.trim().slice(-120)}` },
        ],
      },
    },
    { type: "result", subtype: "success", session_id: sessionId },
  ];
  for (const ev of events) {
    stdout.write(`${JSON.stringify(ev)}\n`);
  }
  // Match the real CLI's behaviour of flushing then exiting.
  stdout.end?.();
});
