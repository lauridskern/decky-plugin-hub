import { createRoot } from "react-dom/client";
import Panel from "../../src/components/Panel";

// Stand-in for Decky's router so the install buttons do something visible.
(window as any).DeckyBackend = {
  call: async (route: string, ...args: any[]) => console.log("[DeckyBackend]", route, JSON.stringify(args).slice(0, 120)),
  addEventListener: () => undefined,
  removeEventListener: () => undefined,
};

createRoot(document.getElementById("root")!).render(
  <div className="qam">
    <div className="qam-title">Plugin Hub</div>
    <Panel />
  </div>,
);
