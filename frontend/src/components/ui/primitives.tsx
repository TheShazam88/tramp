import type { ButtonHTMLAttributes, HTMLAttributes, PropsWithChildren, ReactNode } from "react";
import { Link } from "react-router-dom";

function cx(...tokens: Array<string | false | null | undefined>) {
  return tokens.filter(Boolean).join(" ");
}

export function Surface({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return <div className={cx("surface-card", className)} {...props} />;
}

export function Eyebrow({ children }: PropsWithChildren) {
  return <p className="eyebrow">{children}</p>;
}

export function SectionHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="section-heading">
      <div>
        {eyebrow ? <Eyebrow>{eyebrow}</Eyebrow> : null}
        <h2>{title}</h2>
        {description ? <p>{description}</p> : null}
      </div>
      {action ? <div className="section-action">{action}</div> : null}
    </div>
  );
}

export function Button({
  children,
  variant = "primary",
  to,
  className: customClassName,
  ...buttonProps
}: PropsWithChildren<{
  variant?: "primary" | "secondary" | "ghost";
  to?: string;
  className?: string;
} & ButtonHTMLAttributes<HTMLButtonElement>>) {
  const className = cx(
    "button",
    variant === "secondary" && "button-secondary",
    variant === "ghost" && "button-ghost",
    customClassName,
  );

  if (to && !buttonProps.disabled) {
    return (
      <Link className={className} to={to}>
        {children}
      </Link>
    );
  }

  if (to && buttonProps.disabled) {
    return (
      <span className={className} aria-disabled="true">
        {children}
      </span>
    );
  }

  return (
    <button className={className} {...buttonProps}>
      {children}
    </button>
  );
}

export function Badge({
  children,
  tone = "value",
}: PropsWithChildren<{
  tone?: "value" | "luxury" | "alert" | "muted";
}>) {
  return <span className={cx("badge", `badge-${tone}`)}>{children}</span>;
}

export function StatGrid({
  items,
}: {
  items: Array<{ label: string; value: string; note: string }>;
}) {
  return (
    <div className="stat-grid">
      {items.map((item) => (
        <Surface key={item.label} className="stat-card">
          <p className="stat-label">{item.label}</p>
          <p className="stat-value">{item.value}</p>
          <p className="stat-note">{item.note}</p>
        </Surface>
      ))}
    </div>
  );
}

export function ScoreBar({
  value,
  label = "Luxury score",
}: {
  value: number;
  label?: string;
}) {
  return (
    <div className="score-block">
      <div className="score-meta">
        <span>{label}</span>
        <strong>{value} / 100</strong>
      </div>
      <div className="score-track" aria-hidden="true">
        <div className="score-fill-value" style={{ width: `${Math.max(value - 16, 0)}%` }} />
        <div className="score-fill-luxury" style={{ width: `${Math.min(16, value)}%` }} />
      </div>
    </div>
  );
}

export function InfoList({
  items,
}: {
  items: string[];
}) {
  return (
    <ul className="info-list">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

export function KeyValueList({
  items,
}: {
  items: Array<{ label: string; value: string }>;
}) {
  return (
    <dl className="key-value-list">
      {items.map((item) => (
        <div key={item.label}>
          <dt>{item.label}</dt>
          <dd>{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Dial({
  value,
}: {
  value: number;
}) {
  return (
    <div className="dial-widget">
      <div className="dial-track">
        <div className="dial-knob" style={{ left: `calc(${value * 100}% - 12px)` }} />
      </div>
      <div className="dial-labels">
        <span>Luxury</span>
        <span>Savings</span>
      </div>
    </div>
  );
}

export function PillRow({
  items,
  selected,
}: {
  items: string[];
  selected?: string;
}) {
  return (
    <div className="pill-row">
      {items.map((item) => (
        <span
          key={item}
          className={cx("pill", selected === item && "pill-selected")}
        >
          {item}
        </span>
      ))}
    </div>
  );
}

export function EmptyState({
  title,
  copy,
  action,
}: {
  title: string;
  copy: string;
  action?: ReactNode;
}) {
  return (
    <Surface className="empty-state">
      <h3>{title}</h3>
      <p>{copy}</p>
      {action ? <div className="empty-state-action">{action}</div> : null}
    </Surface>
  );
}
