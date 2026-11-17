import { useEffect, useMemo, useState } from "react";
import { ButtonItem, PanelSection, PanelSectionRow } from "@decky/ui";
import qrcode from "qrcode-generator";

import { SendLinkState, sendLinkState, startSendLink, stopSendLink } from "../api";

/**
 * "Send from your phone": the backend serves a one-page form on the local
 * network (backend/sendlink.py). The panel shows its address and a QR code.
 * A link sent there opens Decky's install dialog on the Deck (index.tsx).
 */
export function SendFromPhone({ visible }: { visible: boolean }) {
  const [state, setState] = useState<SendLinkState | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The page stops by itself after a while; ask again whenever the panel opens.
  useEffect(() => {
    if (!visible) return;
    sendLinkState().then(setState).catch(() => undefined);
  }, [visible]);

  const qr = useMemo(() => {
    if (!state?.url) return null;
    const code = qrcode(0, "M");
    code.addData(state.url);
    code.make();
    return code.createDataURL(4, 4);
  }, [state?.url]);

  const toggle = async () => {
    setBusy(true);
    setError(null);
    try {
      const next = state?.running ? await stopSendLink() : await startSendLink();
      if (next.error) setError(next.error);
      setState(next);
    } catch (err) {
      setError(String((err as Error)?.message ?? err));
    } finally {
      setBusy(false);
    }
  };

  const running = !!state?.running;
  const minutes = state?.expires ? Math.max(1, Math.round((state.expires - Date.now() / 1000) / 60)) : null;

  return (
    <PanelSection title="Send from your phone">
      {!running && (
        <PanelSectionRow>
          <div style={{ fontSize: 13, lineHeight: "18px", color: "#c3c9cf", padding: "0 0 6px" }}>
            The Deck's keyboard can't paste. Open a page on your phone or computer instead, paste the link there, and
            confirm the install here.
          </div>
        </PanelSectionRow>
      )}
      {running && state?.url && (
        <PanelSectionRow>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8, padding: "4px 0 8px" }}>
            {qr && (
              <img
                src={qr}
                alt=""
                style={{ width: 168, height: 168, imageRendering: "pixelated", background: "#fff", borderRadius: 6 }}
              />
            )}
            <div
              style={{
                fontFamily: "monospace",
                fontSize: 13,
                color: "#fff",
                wordBreak: "break-all",
                textAlign: "center",
                userSelect: "text",
              }}
            >
              {state.url}
            </div>
            <div style={{ fontSize: 12, lineHeight: "16px", color: "#8b929a", textAlign: "center" }}>
              {state.ip
                ? "Scan the code or open the address on a phone or computer on the same Wi-Fi."
                : "The Deck's address on your network is unknown; try steamdeck.local or check Settings → Internet."}
              {minutes ? ` Stops by itself in about ${minutes} min.` : ""}
            </div>
          </div>
        </PanelSectionRow>
      )}
      {error && (
        <PanelSectionRow>
          <div style={{ fontSize: 13, color: "#ff8c7a", padding: "2px 0 6px" }}>{error}</div>
        </PanelSectionRow>
      )}
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={busy} onClick={toggle}>
          {busy ? "Working…" : running ? "Stop" : "Show the address"}
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
}
