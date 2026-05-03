import { createElement } from "react";
import { render } from "ink-testing-library";
import { describe, expect, it } from "vitest";
import { ErrorModal } from "../src/components/ErrorModal.js";
import { ERROR_KINDS, type ErrorKind } from "../src/lib/errors/kinds.js";

const KINDS = Object.keys(ERROR_KINDS) as ErrorKind[];

describe("ErrorModal rendering", () => {
  for (const kind of KINDS) {
    it(`renders title + message + hint for kind="${kind}"`, () => {
      const { lastFrame } = render(
        createElement(ErrorModal, {
          kind,
          message: `Sample message for ${kind}`,
        }),
      );
      const frame = lastFrame() ?? "";
      expect(frame).toContain(ERROR_KINDS[kind].defaultTitle);
      expect(frame).toContain(`Sample message for ${kind}`);
      expect(frame).toContain("Hint:");
      // Long hints can wrap across lines depending on terminal width, so
      // assert on the first ~30 chars rather than the whole string.
      const hintHead = ERROR_KINDS[kind].defaultHint.slice(0, 30);
      expect(frame).toContain(hintHead);
    });
  }

  it("uses caller-supplied title and hint overrides", () => {
    const { lastFrame } = render(
      createElement(ErrorModal, {
        kind: "auth-expired",
        title: "Custom title please",
        message: "x",
        hint: "Custom hint please",
      }),
    );
    const frame = lastFrame() ?? "";
    expect(frame).toContain("Custom title please");
    expect(frame).toContain("Custom hint please");
    // Defaults must not leak through when overridden.
    expect(frame).not.toContain(ERROR_KINDS["auth-expired"].defaultTitle);
    expect(frame).not.toContain(ERROR_KINDS["auth-expired"].defaultHint);
  });

  it("omits dismiss / retry hints when callbacks are not provided", () => {
    const { lastFrame } = render(
      createElement(ErrorModal, { kind: "unknown", message: "x" }),
    );
    const frame = lastFrame() ?? "";
    expect(frame).not.toContain("[enter]");
    expect(frame).not.toContain("[r]");
  });

  it("shows dismiss + retry hints when both callbacks are provided", () => {
    const noop = () => {
      /* test stub */
    };
    const { lastFrame } = render(
      createElement(ErrorModal, {
        kind: "pipeline-failure",
        message: "x",
        onDismiss: noop,
        onRetry: noop,
      }),
    );
    const frame = lastFrame() ?? "";
    expect(frame).toContain("[enter] dismiss");
    expect(frame).toContain("[r] retry");
  });
});
