import { addEventListener, definePlugin, removeEventListener, toaster } from "@decky/api";
import { staticClasses } from "@decky/ui";
import { FaGithub } from "react-icons/fa";

import type { Resolved } from "./api";
import Panel from "./components/Panel";
import { requestInstall } from "./decky";

interface UpdateNotice {
  updates: { name: string; from: string | null; to: string }[];
  total: number;
}

export default definePlugin(() => {
  // The backend checks GitHub by itself (every 6 h) and says when a release
  // shows up that it has not reported before. No timers run in here.
  const onUpdates = (notice: UpdateNotice) => {
    const list = notice?.updates ?? [];
    if (!list.length) return;
    toaster.toast({
      title: list.length === 1 ? `${list[0].name} ${list[0].to}` : "Plugin updates",
      body:
        list.length === 1
          ? "An update is ready in Plugin Hub."
          : `${list.length} plugins have updates in Plugin Hub.`,
      icon: <FaGithub />,
    });
  };
  addEventListener<[UpdateNotice]>("plugin_hub_updates", onUpdates);

  // A link sent from the phone page (backend/sendlink.py), already downloaded
  // and checked: show Decky's install dialog on the Deck, panel open or not.
  const onLink = (r: Resolved) => {
    if (!r?.ok) return;
    requestInstall(r).catch((err) =>
      toaster.toast({ title: "Plugin Hub", body: String(err?.message ?? err), icon: <FaGithub /> }),
    );
  };
  addEventListener<[Resolved]>("plugin_hub_link", onLink);

  return {
    name: "Plugin Hub",
    titleView: <div className={staticClasses.Title}>Plugin Hub</div>,
    content: <Panel />,
    icon: <FaGithub />,
    onDismount() {
      removeEventListener("plugin_hub_updates", onUpdates);
      removeEventListener("plugin_hub_link", onLink);
    },
  };
});
