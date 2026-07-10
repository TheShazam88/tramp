interface TrampBrandProps {
  compact?: boolean;
  className?: string;
}

export function TrampBrand({ compact = false, className = "" }: TrampBrandProps) {
  const classes = [
    "tramp-brand",
    compact ? "tramp-brand-compact" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={classes} aria-label="TRAMP, Travel Amplifier">
      <span className="brand-wordmark">TRAMP</span>
      <span className="brand-expansion">TRAVEL AMPLIFIER</span>
    </div>
  );
}
