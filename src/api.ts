import { callable } from "@decky/api";

export interface Latest {
  tag?: string;
  title?: string;
  notes?: string;
  url?: string;
  published_at?: string;
  prerelease?: boolean;
  has_zip?: boolean;
  error?: string;
  kind?: string;
  checked?: number;
}

export type LinkSource = "auto" | "manual" | "install" | "self" | null;

export interface PluginView {
  name: string;
  folder: string;
  version: string | null;
  package_version: string | null;
  author: string | null;
  repo: string | null;
  link: LinkSource;
  detected_repo: string | null;
  root: boolean;
  latest: Latest | null;
  update: boolean;
  /** update | current | unlinked | unchecked | no_zip | no_release | repo_not_found | error … */
  status: string;
  pending: boolean;
  is_self: boolean;
}

export interface HubSettings {
  include_prereleases: boolean;
  auto_check: boolean;
  notify: boolean;
  has_token: boolean;
  token_hint: string;
}

export interface HubState {
  plugins: PluginView[];
  updates: number;
  checked_at: number | null;
  checking: boolean;
  error: { message: string; kind: string; reset?: number | null } | null;
  rate: { remaining: number; limit: number | null; reset: number | null } | null;
  settings: HubSettings;
  plugins_dir: string;
}

export interface PackageInfo {
  path: string;
  file_url: string;
  sha256: string;
  size: number;
  folder: string;
  name: string;
  version: string | null;
  author: string | null;
  description: string | null;
  root: boolean;
  warnings: string[];
}

export interface Resolved {
  ok: boolean;
  error?: string;
  kind?: string;
  reset?: number | null;
  repo?: string;
  tag?: string;
  title?: string;
  notes?: string;
  prerelease?: boolean;
  name?: string;
  version?: string;
  installed_version?: string | null;
  /** Decky's InstallType: 0 install, 1 reinstall, 2 update, 3 downgrade. */
  install_type?: number;
  package?: PackageInfo;
}

export const getState = callable<[], HubState>("get_state");
export const checkUpdates = callable<[force: boolean], HubState>("check_updates");
export const resolve = callable<[link: string], Resolved>("resolve");
export const prepareUpdate = callable<[name: string], Resolved>("prepare_update");
export const prepareUpdates = callable<[], Resolved[]>("prepare_updates");
export const cancelInstall = callable<[name: string], void>("cancel_install");
export const linkRepo = callable<[name: string, link: string], { ok: boolean; error?: string; repo?: string }>("link_repo");
export const unlinkRepo = callable<[name: string], HubState>("unlink_repo");
export const forgetPlugin = callable<[name: string], HubState>("forget_plugin");
export const setSettings = callable<[changes: Partial<HubSettings> & { github_token?: string }], HubState>("set_settings");

export interface SendLinkState {
  running: boolean;
  url: string | null;
  ip: string | null;
  port: number | null;
  code: string | null;
  /** unix seconds */
  expires: number | null;
  error?: string;
}

export const startSendLink = callable<[], SendLinkState>("start_send_link");
export const stopSendLink = callable<[], SendLinkState>("stop_send_link");
export const sendLinkState = callable<[], SendLinkState>("send_link_state");
