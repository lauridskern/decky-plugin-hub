/**
 * Stand-in for @decky/ui: just enough of the Quick Access menu's look to
 * judge the panel's layout in Chromium. Not Steam's focus engine.
 */
import { CSSProperties, ReactNode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";

export const staticClasses = { Title: "DeckyTitle" } as Record<string, string>;

export const PanelSection = ({ title, children }: { title?: ReactNode; children?: ReactNode }) => (
  <div className="qam-section">
    {title ? <div className="qam-section-title">{title}</div> : null}
    {children}
  </div>
);

export const PanelSectionRow = ({ children }: { children?: ReactNode }) => <div className="qam-row">{children}</div>;

interface ItemProps {
  label?: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  layout?: "below" | "inline";
  disabled?: boolean;
  onClick?: (e: any) => void;
  bottomSeparator?: string;
}

export const ButtonItem = ({ label, description, children, layout, disabled, onClick }: ItemProps) => (
  <div className={`qam-item ${layout === "below" ? "below" : ""}`}>
    {label || description ? (
      <div className="qam-item-text">
        {label ? <div className="qam-label">{label}</div> : null}
        {description ? <div className="qam-desc">{description}</div> : null}
      </div>
    ) : null}
    <button className="qam-button" disabled={disabled} onClick={onClick} tabIndex={0}>
      {children}
    </button>
  </div>
);

export const Field = ({
  label,
  description,
  children,
  focusable,
  onClick,
  onActivate,
  bottomSeparator,
}: ItemProps & { focusable?: boolean; highlightOnFocus?: boolean; onActivate?: (e: any) => void }) => (
  <div
    className={`qam-item field ${focusable ? "focusable" : ""} ${bottomSeparator === "none" ? "nosep" : ""}`}
    tabIndex={focusable ? 0 : undefined}
    onClick={onActivate ?? onClick}
  >
    <div className="qam-item-text">
      {label ? <div className="qam-label">{label}</div> : null}
      {description ? <div className="qam-desc">{description}</div> : null}
    </div>
    {children ? <div className="qam-inline">{children}</div> : null}
  </div>
);

export const TextField = ({
  label,
  description,
  value,
  onChange,
  onKeyDown,
  bIsPassword,
  disabled,
}: {
  label?: ReactNode;
  description?: ReactNode;
  value?: string;
  onChange?: (e: any) => void;
  onKeyDown?: (e: any) => void;
  bIsPassword?: boolean;
  disabled?: boolean;
}) => (
  <div className="qam-item below nosep">
    {label ? <div className="qam-label">{label}</div> : null}
    <input
      className="qam-input"
      type={bIsPassword ? "password" : "text"}
      value={value}
      disabled={disabled}
      onChange={onChange}
      onKeyDown={onKeyDown}
    />
    {description ? <div className="qam-desc">{description}</div> : null}
  </div>
);

export const ToggleField = ({
  label,
  description,
  checked,
  onChange,
}: ItemProps & { checked: boolean; onChange?: (on: boolean) => void }) => (
  <div className="qam-item">
    <div className="qam-item-text">
      <div className="qam-label">{label}</div>
      {description ? <div className="qam-desc">{description}</div> : null}
    </div>
    <button className={`qam-toggle ${checked ? "on" : ""}`} onClick={() => onChange?.(!checked)} tabIndex={0}>
      <span />
    </button>
  </div>
);

export const Focusable = ({ children, style }: { children?: ReactNode; style?: CSSProperties; [k: string]: any }) => (
  <div style={style}>{children}</div>
);

export const DialogButton = ({ children, onClick, disabled }: { children?: ReactNode; onClick?: () => void; disabled?: boolean }) => (
  <button className="qam-button dialog" disabled={disabled} onClick={onClick}>
    {children}
  </button>
);

export const ModalRoot = ({ children }: { children?: ReactNode; onCancel?: () => void; closeModal?: () => void }) => (
  <div className="modal-backdrop">
    <div className="modal">{children}</div>
  </div>
);

export const ConfirmModal = ({
  strTitle,
  strDescription,
  strOKButtonText,
  strCancelButtonText,
  onOK,
  closeModal,
}: any) => (
  <ModalRoot>
    <div style={{ fontSize: 22, fontWeight: 700, marginBottom: 8 }}>{strTitle}</div>
    <div style={{ marginBottom: 16 }}>{strDescription}</div>
    <div style={{ display: "flex", gap: 8 }}>
      <DialogButton onClick={() => { onOK?.(); closeModal?.(); }}>{strOKButtonText ?? "OK"}</DialogButton>
      <DialogButton onClick={() => closeModal?.()}>{strCancelButtonText ?? "Cancel"}</DialogButton>
    </div>
  </ModalRoot>
);

/** Renders the modal into its own root, like Steam's modal manager. */
export function showModal(modal: any) {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const close = () => {
    root.unmount();
    host.remove();
  };
  function Holder() {
    const [el] = useState(() => ({ ...modal, props: { ...modal.props, closeModal: close } }));
    useEffect(() => undefined, []);
    return el;
  }
  root.render(<Holder />);
  return { Close: close, Update: () => undefined };
}
