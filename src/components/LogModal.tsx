import { useEffect, useRef, useState } from "react";
import { DialogButton, Focusable, ModalRoot } from "@decky/ui";

import { PluginLog, pluginLog } from "../api";
import { ago } from "../format";

/**
 * A plugin's newest log (backend/logs.py), so a plugin that does not load can
 * be looked into in Game Mode. The d-pad scrolls; the phone page has the same
 * text for copying.
 */
export function LogModal({ name, closeModal }: { name: string; closeModal?: () => void }) {
  const [log, setLog] = useState<PluginLog | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const close = () => closeModal?.();

  const load = () => {
    setLog(null);
    pluginLog(name, 300)
      .then(setLog)
      .catch((error) => setLog({ ok: false, error: String(error) }));
  };
  useEffect(load, [name]);
  // Newest lines are at the bottom: start there.
  useEffect(() => {
    if (box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [log]);

  const scroll = (by: number) => box.current?.scrollBy({ top: by });

  return (
    <ModalRoot onCancel={close} closeModal={close}>
      <div style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>{name}: log</div>
      <div style={{ fontSize: 12, color: "#8b929a", marginBottom: 8, wordBreak: "break-all" }}>
        {log?.ok ? `${log.file} · written ${ago(log.mtime ?? 0)}` : log ? "" : "Reading…"}
      </div>
      <div
        ref={box}
        style={{
          height: 340,
          overflowY: "auto",
          background: "#0b0f14",
          borderRadius: 6,
          padding: 10,
          fontFamily: "monospace",
          fontSize: 11,
          lineHeight: "15px",
          whiteSpace: "pre-wrap",
          wordBreak: "break-all",
          color: log && !log.ok ? "#ff8c7a" : "#d6dde4",
          userSelect: "text",
        }}
      >
        {log ? (log.ok ? log.text || "(empty)" : log.error) : ""}
      </div>
      <div style={{ fontSize: 12, color: "#8b929a", margin: "8px 0" }}>
        To copy it: Send from your phone → Plugin logs.
      </div>
      <Focusable flow-children="row" style={{ display: "flex", gap: 8 }}>
        <DialogButton onClick={() => scroll(-300)}>Up</DialogButton>
        <DialogButton onClick={() => scroll(300)}>Down</DialogButton>
        <DialogButton onClick={load}>Reload</DialogButton>
        <DialogButton onClick={close}>Close</DialogButton>
      </Focusable>
    </ModalRoot>
  );
}
