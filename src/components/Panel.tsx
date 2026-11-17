import { useCallback, useEffect, useRef, useState } from "react";
import { addEventListener, removeEventListener, useQuickAccessVisible } from "@decky/api";
import { ButtonItem, Field, PanelSection, PanelSectionRow, showModal, TextField, ToggleField } from "@decky/ui";

import {
  checkUpdates,
  getState,
  HubSettings,
  HubState,
  prepareUpdate,
  prepareUpdates,
  PluginView,
  resolve,
  Resolved,
  setSettings,
} from "../api";
import { onInstallFinished, requestInstall, requestInstalls } from "../decky";
import { ago, statusLine, until, v } from "../format";
import { PluginModal } from "./PluginModal";
import { SendFromPhone } from "./SendFromPhone";

type Tone = "info" | "ok" | "error";
interface Line {
  text: string;
  tone: Tone;
}

const toneColor: Record<Tone, string> = { info: "#c3c9cf", ok: "#8fd18f", error: "#ff8c7a" };

function StateLine({ line }: { line: Line | null }) {
  if (!line) return null;
  return (
    <PanelSectionRow>
      <div style={{ fontSize: 13, lineHeight: "18px", color: toneColor[line.tone], padding: "2px 0 6px", whiteSpace: "pre-line" }}>
        {line.text}
      </div>
    </PanelSectionRow>
  );
}

/**
 * Game Mode's keyboard has no paste key, so the panel offers a Paste button
 * that reads the clipboard itself. Whether the Steam client lets a plugin do
 * that is only known after trying; after a refusal the button goes away for
 * this session and the phone page is offered instead.
 */
let clipboardWorks: boolean | undefined;
const canTryClipboard = () =>
  clipboardWorks !== false && typeof navigator !== "undefined" && typeof navigator.clipboard?.readText === "function";

async function readClipboard(): Promise<string> {
  const timeout = new Promise<never>((_, reject) => setTimeout(() => reject(new Error("timeout")), 2500));
  return Promise.race([navigator.clipboard.readText(), timeout]);
}

const errorText = (err: unknown) => String((err as Error)?.message ?? err);

const installWord = (r: Resolved) =>
  r.install_type === 2 ? "Update" : r.install_type === 1 ? "Reinstall" : r.install_type === 3 ? "Downgrade" : "Install";

export default function Panel() {
  const [state, setState] = useState<HubState | null>(null);
  const [link, setLink] = useState("");
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [installLine, setInstallLine] = useState<Line | null>(null);
  const [updateLine, setUpdateLine] = useState<Line | null>(null);
  const [canPaste, setCanPaste] = useState(canTryClipboard);
  const visible = useQuickAccessVisible();
  const alive = useRef(true);

  const apply = useCallback((next: HubState | null | undefined) => {
    if (next && alive.current) setState(next);
  }, []);

  const reload = useCallback(() => getState().then(apply).catch(() => undefined), [apply]);

  // Opening the panel shows what is known at once, then asks GitHub if the
  // last check is older than an hour (the backend decides).
  useEffect(() => {
    if (!visible) return;
    reload();
    checkUpdates(false).then(apply).catch(() => undefined);
  }, [visible, reload, apply]);

  // Decky says when it finished installing something: show the new version.
  useEffect(() => {
    alive.current = true;
    const off = onInstallFinished(() => {
      reload();
      setInstallLine(null);
    });
    return () => {
      alive.current = false;
      off();
    };
  }, [reload]);

  // A link from the phone page: index.tsx already asked Decky to install it.
  useEffect(() => {
    const onLink = (r: Resolved) => {
      if (!r?.ok || !alive.current) return;
      setInstallLine({ text: `${installWord(r)} ${r.name} ${r.version} (sent from your phone): confirm in Decky's dialog.`, tone: "ok" });
      reload();
    };
    addEventListener<[Resolved]>("plugin_hub_link", onLink);
    return () => removeEventListener("plugin_hub_link", onLink);
  }, [reload]);

  const paste = async () => {
    try {
      const text = (await readClipboard()).trim();
      clipboardWorks = true;
      if (!text) return setInstallLine({ text: "The clipboard is empty.", tone: "info" });
      setLink(text);
      setInstallLine(null);
    } catch {
      clipboardWorks = false;
      setCanPaste(false);
      setInstallLine({
        text: "The Steam client doesn't let plugins read the clipboard. Use \"Send from your phone\" below.",
        tone: "error",
      });
    }
  };

  const install = async () => {
    const text = link.trim();
    if (!text || busy) return;
    setBusy("install");
    setInstallLine({ text: "Finding the latest release and downloading it…", tone: "info" });
    try {
      const r = await resolve(text);
      if (!r.ok) {
        setInstallLine({ text: r.error ?? "Could not install that.", tone: "error" });
        return;
      }
      const warn = [...(r.package?.warnings ?? []), r.package?.root ? "This plugin runs as root." : ""].filter(Boolean);
      setInstallLine({
        text: `${installWord(r)} ${r.name} ${r.version}: confirm in Decky's dialog.${warn.length ? "\n" + warn.join(" ") : ""}`,
        tone: "ok",
      });
      await requestInstall(r);
      setLink("");
      reload();
    } catch (err) {
      setInstallLine({ text: errorText(err), tone: "error" });
    } finally {
      setBusy(null);
    }
  };

  const updateOne = async (p: PluginView) => {
    setBusy(`update:${p.name}`);
    setUpdateLine({ text: `Downloading ${p.name} ${p.latest?.tag ?? ""}…`, tone: "info" });
    try {
      const r = await prepareUpdate(p.name);
      if (!r.ok) return setUpdateLine({ text: r.error ?? "Could not update.", tone: "error" });
      setUpdateLine({ text: `Confirm the update in Decky's dialog.`, tone: "ok" });
      await requestInstall(r);
    } catch (err) {
      setUpdateLine({ text: errorText(err), tone: "error" });
    } finally {
      setBusy(null);
    }
  };

  const updateAll = async () => {
    setBusy("all");
    setUpdateLine({ text: "Downloading every update…", tone: "info" });
    try {
      const results = await prepareUpdates();
      const ready = results.filter((r) => r.ok);
      const failed = results.filter((r) => !r.ok);
      if (ready.length) await requestInstalls(ready);
      setUpdateLine({
        text: [
          ready.length ? `Confirm ${ready.length} update${ready.length === 1 ? "" : "s"} in Decky's dialog.` : "",
          ...failed.map((r) => r.error ?? "An update failed."),
        ]
          .filter(Boolean)
          .join("\n"),
        tone: failed.length && !ready.length ? "error" : "ok",
      });
    } catch (err) {
      setUpdateLine({ text: errorText(err), tone: "error" });
    } finally {
      setBusy(null);
    }
  };

  const checkNow = async () => {
    setBusy("check");
    setUpdateLine(null);
    try {
      apply(await checkUpdates(true));
    } catch (err) {
      setUpdateLine({ text: errorText(err), tone: "error" });
    } finally {
      setBusy(null);
    }
  };

  const change = async (changes: Partial<HubSettings> & { github_token?: string }) => {
    apply(await setSettings(changes));
  };

  const open = (p: PluginView) => showModal(<PluginModal plugin={p} onChanged={reload} />);

  const plugins = state?.plugins ?? [];
  const updates = plugins.filter((p) => p.update);
  const checking = busy === "check" || !!state?.checking;
  const settings = state?.settings;

  return (
    <>
      <PanelSection title="Install from GitHub">
        <PanelSectionRow>
          <TextField
            label="GitHub link"
            description="github.com/owner/repo, owner/repo, or a release link"
            value={link}
            disabled={busy === "install"}
            onChange={(e) => setLink(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") install();
            }}
          />
        </PanelSectionRow>
        {canPaste && (
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={!!busy} onClick={paste}>
              Paste
            </ButtonItem>
          </PanelSectionRow>
        )}
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={!link.trim() || !!busy} onClick={install}>
            {busy === "install" ? "Working…" : "Install latest release"}
          </ButtonItem>
        </PanelSectionRow>
        <StateLine line={installLine} />
      </PanelSection>

      <SendFromPhone visible={visible} />

      <PanelSection title={updates.length ? `Updates (${updates.length})` : "Updates"}>
        {state?.error && (
          <StateLine
            line={{
              text: state.error.kind === "rate_limited" && state.error.reset
                ? `GitHub's limit is used up; it resets in ${until(state.error.reset)}. A token in Settings raises it.`
                : state.error.message,
              tone: "error",
            }}
          />
        )}
        {updates.map((p) => (
          <PanelSectionRow key={p.name}>
            <ButtonItem
              layout="below"
              label={p.name}
              description={
                <span style={{ whiteSpace: "pre-line" }}>
                  {`${v(p.version)} → ${p.latest?.tag ?? "?"}`}
                  {p.latest?.notes ? `\n${p.latest.notes}` : ""}
                </span>
              }
              disabled={!!busy}
              onClick={() => updateOne(p)}
            >
              {busy === `update:${p.name}` ? "Downloading…" : `Update to ${p.latest?.tag ?? "latest"}`}
            </ButtonItem>
          </PanelSectionRow>
        ))}
        {updates.length > 1 && (
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={!!busy} onClick={updateAll}>
              {busy === "all" ? "Downloading…" : `Update all (${updates.length})`}
            </ButtonItem>
          </PanelSectionRow>
        )}
        {!updates.length && (
          <PanelSectionRow>
            <Field
              label={checking ? "Checking GitHub…" : "Everything is up to date"}
              description={`Last checked ${ago(state?.checked_at)}`}
              bottomSeparator="none"
            />
          </PanelSectionRow>
        )}
        <StateLine line={updateLine} />
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={!!busy} onClick={checkNow}>
            {checking ? "Checking…" : "Check for updates"}
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title={`Installed (${plugins.length})`}>
        {plugins.map((p) => (
          <PanelSectionRow key={p.folder}>
            <Field
              label={p.name}
              description={
                <span>
                  {statusLine(p)}
                  <br />
                  <span style={{ color: "#8b929a" }}>{p.repo ?? "Press A to link a GitHub repository"}</span>
                </span>
              }
              focusable
              highlightOnFocus
              // Steam fires onActivate for A and for a tap; onClick too would open it twice.
              onActivate={() => open(p)}
            >
              {p.update ? <span style={{ color: "#59bf40", fontWeight: 700, fontSize: 13 }}>UPDATE</span> : null}
            </Field>
          </PanelSectionRow>
        ))}
        {state && !plugins.length && (
          <PanelSectionRow>
            <Field label="No plugins found" description={state.plugins_dir} bottomSeparator="none" />
          </PanelSectionRow>
        )}
      </PanelSection>

      <PanelSection title="Settings">
        <PanelSectionRow>
          <ToggleField
            label="Check for updates by itself"
            description="Every 6 hours, while the Deck is on"
            checked={!!settings?.auto_check}
            onChange={(on) => change({ auto_check: on })}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <ToggleField
            label="Notify me about updates"
            checked={!!settings?.notify}
            onChange={(on) => change({ notify: on })}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <ToggleField
            label="Include pre-releases"
            checked={!!settings?.include_prereleases}
            onChange={(on) => change({ include_prereleases: on })}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <TextField
            label="GitHub token (optional)"
            description={
              settings?.has_token
                ? `Saved (${settings.token_hint || "set"}). Raises GitHub's limit to 5000 checks an hour.`
                : "Without one GitHub allows 60 checks an hour. A token with no scopes is enough."
            }
            bIsPassword
            value={token}
            onChange={(e) => setToken(e.target.value)}
          />
        </PanelSectionRow>
        {token.trim() ? (
          <PanelSectionRow>
            <ButtonItem
              layout="below"
              onClick={async () => {
                await change({ github_token: token.trim() });
                setToken("");
              }}
            >
              Save token
            </ButtonItem>
          </PanelSectionRow>
        ) : settings?.has_token ? (
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={() => change({ github_token: "" })}>
              Remove token
            </ButtonItem>
          </PanelSectionRow>
        ) : null}
        {state?.rate && (
          <PanelSectionRow>
            <Field
              label="GitHub requests left"
              bottomSeparator="none"
            >
              <span style={{ fontSize: 13 }}>
                {state.rate.remaining}
                {state.rate.limit ? ` / ${state.rate.limit}` : ""}
              </span>
            </Field>
          </PanelSectionRow>
        )}
      </PanelSection>
    </>
  );
}
