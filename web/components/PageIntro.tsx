import type { ReactNode } from "react";
import Icon, { type IconName } from "./Icon";

export default function PageIntro({ eyebrow, title, description, icon, children }: {
  eyebrow: string; title: string; description: string; icon: IconName; children?: ReactNode;
}) {
  return <header className="page-intro">
    <div className="page-intro-copy"><span className="page-mark"><Icon name={icon} size={24} /></span>
      <p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p className="page-description">{description}</p></div>
    {children && <div className="page-actions">{children}</div>}
  </header>;
}
