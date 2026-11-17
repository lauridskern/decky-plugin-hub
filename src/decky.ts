/**
 * Decky Loader's own installer, reached through its websocket router.
 *
 * `window.DeckyBackend` is the loader's WSRouter (decky-loader
 * frontend/src/index.ts). The routes used here are the ones Decky's store and
 * "Install from URL" use (frontend/src/plugin.ts, backend utilities.py):
 *
 *   utilities/install_plugin   (artifact, name, version, hash, install_type)
 *   utilities/install_plugins  ([{ artifact, name, version, hash, install_type }])
 *   utilities/uninstall_plugin (name)
 *
 * Both install routes only *ask*: Decky shows its own confirm dialog and
 * installs when the user accepts. With a `file://` artifact Decky reads the
 * zip the hub already downloaded, checks it against `hash` (sha256), and does
 * not report an install to its plugin store.
 */
import type { Resolved } from "./api";

interface DeckyRouter {
  call: (route: string, ...args: any[]) => Promise<any>;
  addEventListener?: (event: string, listener: (...args: any[]) => any) => void;
  removeEventListener?: (event: string, listener: (...args: any[]) => any) => void;
}

/** decky-loader frontend/src/plugin.ts InstallType */
export const InstallType = { INSTALL: 0, REINSTALL: 1, UPDATE: 2, DOWNGRADE: 3, OVERWRITE: 4 } as const;

function router(): DeckyRouter {
  const backend = (window as unknown as { DeckyBackend?: DeckyRouter }).DeckyBackend;
  if (!backend || typeof backend.call !== "function") {
    throw new Error("This Decky Loader version has no installer the hub can reach. Update Decky Loader.");
  }
  return backend;
}

function request(r: Resolved) {
  if (!r.ok || !r.package || !r.name) throw new Error(r.error ?? "Nothing to install");
  const installType = r.install_type ?? InstallType.INSTALL;
  return {
    artifact: r.package.file_url,
    name: r.name,
    version: r.version ?? r.tag ?? "unknown",
    hash: r.package.sha256,
    install_type: installType,
    // The frontend's own type spells it this way; Decky only reads the above.
    installType,
  };
}

/** Shows Decky's confirm dialog for one plugin. */
export async function requestInstall(r: Resolved): Promise<void> {
  const req = request(r);
  await router().call("utilities/install_plugin", req.artifact, req.name, req.version, req.hash, req.install_type);
}

/** One confirm dialog for several plugins (Decky's multi-install prompt). */
export async function requestInstalls(list: Resolved[]): Promise<void> {
  if (list.length === 1) return requestInstall(list[0]);
  await router().call("utilities/install_plugins", list.map(request));
}

export async function uninstall(name: string): Promise<void> {
  await router().call("utilities/uninstall_plugin", name);
}

/** Called with the plugin's name each time Decky finishes an install. */
export function onInstallFinished(listener: (name: string) => void): () => void {
  const backend = (window as unknown as { DeckyBackend?: DeckyRouter }).DeckyBackend;
  if (!backend?.addEventListener || !backend.removeEventListener) return () => undefined;
  const handler = (name: string) => listener(name);
  backend.addEventListener("loader/plugin_download_finish", handler);
  return () => backend.removeEventListener?.("loader/plugin_download_finish", handler);
}
