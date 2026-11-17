import type { PluginView } from "./api";

export function ago(seconds: number | null | undefined): string {
  if (!seconds) return "never";
  const diff = Math.max(0, Date.now() / 1000 - seconds);
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.round(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)} h ago`;
  return `${Math.round(diff / 86400)} d ago`;
}

export function until(epoch: number | null | undefined): string {
  if (!epoch) return "";
  const minutes = Math.max(1, Math.round((epoch - Date.now() / 1000) / 60));
  return `${minutes} min`;
}

export const v = (text: string | null | undefined) => (text ? (/^\d/.test(text) ? `v${text}` : text) : "?");

/** One line about where a plugin stands. */
export function statusLine(p: PluginView): string {
  switch (p.status) {
    case "update":
      return `${v(p.version)} → ${p.latest?.tag ?? "?"}`;
    case "current":
      return `${v(p.version)} · up to date`;
    case "unlinked":
      return `${v(p.version)} · not linked to GitHub`;
    case "unchecked":
      return `${v(p.version)} · not checked yet`;
    case "no_zip":
      return `${v(p.version)} · latest release has no plugin zip`;
    case "no_release":
      return `${v(p.version)} · no releases on GitHub`;
    case "repo_not_found":
      return `${v(p.version)} · repository not found`;
    case "bad_token":
      return `${v(p.version)} · GitHub refused the token`;
    default:
      return `${v(p.version)} · ${p.latest?.error ?? "could not check"}`;
  }
}

export const linkLabel: Record<string, string> = {
  auto: "found in the plugin's files",
  manual: "linked by you",
  install: "installed from here",
  self: "this plugin",
};
