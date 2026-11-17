import { addEventListener, definePlugin, removeEventListener, toaster } from "@decky/api";
import { staticClasses } from "@decky/ui";
import { FaGithub } from "react-icons/fa";

import Panel from "./components/Panel";

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

  return {
    name: "Plugin Hub",
    titleView: <div className={staticClasses.Title}>Plugin Hub</div>,
    content: <Panel />,
    icon: <FaGithub />,
    onDismount() {
      removeEventListener("plugin_hub_updates", onUpdates);
    },
  };
});
