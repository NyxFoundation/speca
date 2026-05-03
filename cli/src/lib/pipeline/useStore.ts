/**
 * React adapter around the external `PipelineStore`. We use
 * `useSyncExternalStore` so we get tear-free reads and don't need to
 * mirror state into React.
 */
import { useSyncExternalStore } from "react";
import type { PipelineSnapshot, PipelineStore } from "./store.js";

export function usePipelineStore(store: PipelineStore): PipelineSnapshot {
  return useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
}
