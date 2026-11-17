import { useState } from "react";
import { ConfirmModal, DialogButton, Focusable, ModalRoot, showModal, TextField } from "@decky/ui";

import { forgetPlugin, linkRepo, PluginView, prepareUpdate, unlinkRepo } from "../api";
import { requestInstall, uninstall } from "../decky";
import { linkLabel, statusLine, v } from "../format";
import { LogModal } from "./LogModal";

interface Props {
  plugin: PluginView;
  closeModal?: () => void;
  onChanged: () => void;
}

const row: React.CSSProperties = { display: "flex", justifyContent: "space-between", gap: 16, padding: "3px 0" };
const muted: React.CSSProperties = { color: "#8b929a" };

/** Everything that can be done with one installed plugin. */
export function PluginModal({ plugin, closeModal, onChanged }: Props) {
  const [repo, setRepo] = useState(plugin.repo ?? "");
  const [message, setMessage] = useState<{ text: string; error?: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const close = () => closeModal?.();

  const save = async () => {
    if (!repo.trim()) return;
    setBusy(true);
    const res = await linkRepo(plugin.name, repo.trim());
    setBusy(false);
    if (!res.ok) return setMessage({ text: res.error ?? "Not a GitHub link", error: true });
    onChanged();
    close();
  };

  const unlink = async () => {
    await unlinkRepo(plugin.name);
    onChanged();
    close();
  };

  const reinstall = async () => {
    setBusy(true);
    setMessage({ text: "Downloading the release…" });
    const res = await prepareUpdate(plugin.name);
    setBusy(false);
    if (!res.ok) return setMessage({ text: res.error ?? "Could not get the release", error: true });
    close();
    try {
      await requestInstall(res);
    } catch (err) {
      setMessage({ text: String((err as Error).message ?? err), error: true });
    }
  };

  const remove = () =>
    showModal(
      <ConfirmModal
        strTitle={`Uninstall ${plugin.name}?`}
        strDescription="Decky removes the plugin's files. Its settings folder stays."
        strOKButtonText="Uninstall"
        strCancelButtonText="Keep"
        bAlertDialog
        onOK={async () => {
          // Forget first: uninstalling the hub itself stops this backend.
          await forgetPlugin(plugin.name).catch(() => undefined);
          close();
          try {
            await uninstall(plugin.name);
          } finally {
            onChanged();
          }
        }}
      />,
    );

  const action = plugin.update ? `Update to ${plugin.latest?.tag}` : "Reinstall the latest release";

  return (
    <ModalRoot onCancel={close} closeModal={close}>
      <div style={{ fontSize: 22, fontWeight: 700, marginBottom: 8 }}>{plugin.name}</div>
      <div style={{ fontSize: 14, marginBottom: 12 }}>
        <div style={row}>
          <span style={muted}>Installed</span>
          <span>{v(plugin.version)}</span>
        </div>
        <div style={row}>
          <span style={muted}>Latest release</span>
          <span>{plugin.latest?.tag ?? "—"}</span>
        </div>
        <div style={row}>
          <span style={muted}>Repository</span>
          <span>
            {plugin.repo ?? "not linked"}
            {plugin.link ? <span style={muted}> · {linkLabel[plugin.link] ?? plugin.link}</span> : null}
          </span>
        </div>
        <div style={row}>
          <span style={muted}>Folder</span>
          <span>{plugin.folder}</span>
        </div>
        <div style={{ ...muted, marginTop: 6 }}>{statusLine(plugin)}</div>
        {plugin.update && plugin.latest?.notes ? (
          <div style={{ whiteSpace: "pre-line", marginTop: 8, fontSize: 13, color: "#c3c9cf" }}>{plugin.latest.notes}</div>
        ) : null}
      </div>

      {!plugin.is_self && (
        <TextField
          label="GitHub repository"
          description="owner/repo or a github.com link"
          value={repo}
          onChange={(e) => setRepo(e.target.value)}
        />
      )}

      {message && (
        <div style={{ margin: "8px 0", color: message.error ? "#ff8c7a" : "#c3c9cf", fontSize: 14 }}>{message.text}</div>
      )}

      <Focusable flow-children="column" style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 12 }}>
        {!plugin.is_self && repo.trim() && repo.trim() !== plugin.repo && (
          <DialogButton disabled={busy} onClick={save}>
            Link to {repo.trim()}
          </DialogButton>
        )}
        {plugin.repo && (
          <DialogButton disabled={busy} onClick={reinstall}>
            {action}
          </DialogButton>
        )}
        {plugin.repo && !plugin.is_self && (
          <DialogButton disabled={busy} onClick={unlink}>
            Unlink from GitHub
          </DialogButton>
        )}
        <DialogButton disabled={busy} onClick={() => showModal(<LogModal name={plugin.name} />)}>
          View log
        </DialogButton>
        <DialogButton disabled={busy} onClick={remove}>
          Uninstall…
        </DialogButton>
      </Focusable>
    </ModalRoot>
  );
}
