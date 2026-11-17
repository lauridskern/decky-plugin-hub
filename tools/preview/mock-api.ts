/** Mock of @decky/api for the preview: one update available, three plugins. */
import type { HubState, Resolved } from "../../src/api";

const now = Date.now() / 1000;

const state: HubState = {
  plugins: [
    {
      name: "CSS Loader",
      folder: "SDH-CssLoader",
      version: "2.1.2",
      package_version: "2.1.2",
      author: "Suchmememanyskill",
      repo: null,
      link: null,
      detected_repo: null,
      root: false,
      latest: null,
      update: false,
      status: "unlinked",
      pending: false,
      is_self: false,
    },
    {
      name: "Plugin-Hub",
      folder: "decky-plugin-hub",
      version: "v0.1.0",
      package_version: "0.1.0",
      author: "Laurids Kern",
      repo: "lauridskern/decky-plugin-hub",
      link: "self",
      detected_repo: "lauridskern/decky-plugin-hub",
      root: false,
      latest: { tag: "v0.1.0", has_zip: true, notes: "", checked: now - 300 },
      update: false,
      status: "current",
      pending: false,
      is_self: true,
    },
    {
      name: "ROM-Store",
      folder: "rom-store-decky",
      version: "v1.17.5",
      package_version: "1.17.5",
      author: "ROM Store contributors",
      repo: "lauridskern/decky-rom-store",
      link: "install",
      detected_repo: null,
      root: false,
      latest: {
        tag: "v1.18.2",
        title: "ROM Store v1.18.2",
        notes: "• Play button in the Library\n• Sources ship without addresses\n• Faster cover loading",
        has_zip: true,
        checked: now - 300,
      },
      update: true,
      status: "update",
      pending: false,
      is_self: false,
    },
  ],
  updates: 1,
  checked_at: now - 300,
  checking: false,
  error: null,
  rate: { remaining: 54, limit: 60, reset: now + 1800 },
  settings: { include_prereleases: false, auto_check: true, notify: true, has_token: false, token_hint: "" },
  plugins_dir: "/home/deck/homebrew/plugins",
};

const resolved: Resolved = {
  ok: true,
  repo: "lauridskern/decky-rom-store",
  tag: "v1.18.2",
  name: "ROM-Store",
  version: "v1.18.2",
  install_type: 2,
  package: {
    path: "/tmp/x.zip",
    file_url: "file:///tmp/x.zip",
    sha256: "0".repeat(64),
    size: 1,
    folder: "rom-store-decky",
    name: "ROM-Store",
    version: "1.18.2",
    author: null,
    description: null,
    root: false,
    warnings: [],
  },
};

const handlers: Record<string, (...args: any[]) => any> = {
  get_state: () => state,
  check_updates: () => state,
  resolve: () => resolved,
  prepare_update: () => resolved,
  prepare_updates: () => [resolved],
  cancel_install: () => undefined,
  link_repo: (_n: string, link: string) => ({ ok: true, repo: link }),
  unlink_repo: () => state,
  forget_plugin: () => state,
  plugin_log: (name: string) => ({
    ok: true, name, folder: "rom-store-decky", file: "/home/deck/homebrew/logs/rom-store-decky/2026-11-18 09.12.03.log",
    mtime: Date.now() / 1000 - 120, size: 18000,
    text: [
      "[ROM-Store] INFO ROM Store backend started",
      "[ROM-Store] INFO ROM library root: /home/deck/Emulation/roms (exists=True)",
      "[ROM-Store] ERROR Failed to start ROM-Store!",
      "Traceback (most recent call last):",
      '  File "/home/deck/homebrew/plugins/rom-store-decky/main.py", line 118, in _main',
      "    library = plugin.service.library()",
      "PermissionError: [Errno 13] Permission denied: '/run/media/deck/SD/Emulation/roms'",
    ].join("\n"),
  }),
  start_send_link: () => (sendLink = { ...sendLinkOn, expires: Date.now() / 1000 + 15 * 60 }),
  stop_send_link: () => (sendLink = { running: false, url: null, ip: null, port: null, code: null, expires: null }),
  send_link_state: () => sendLink,
  set_settings: (changes: any) => {
    Object.assign(state.settings, changes);
    return { ...state };
  },
};

const sendLinkOn = { running: true, url: "http://192.168.1.42:8787/k7m2qp", ip: "192.168.1.42", port: 8787, code: "k7m2qp", expires: 0 };
let sendLink: any = { running: false, url: null, ip: null, port: null, code: null, expires: null };

export const callable =
  <Args extends any[] = [], Return = void>(route: string) =>
  async (...args: Args): Promise<Return> => {
    await new Promise((r) => setTimeout(r, 30));
    const handler = handlers[route];
    if (!handler) throw new Error(`No mock for ${route}`);
    return handler(...args) as Return;
  };

export const toaster = { toast: (t: any) => (console.log("[toast]", t.title), { dismiss: () => undefined }) };
export const definePlugin = (fn: any) => fn;
export const addEventListener = () => () => undefined;
export const removeEventListener = () => undefined;
export const useQuickAccessVisible = () => true;
