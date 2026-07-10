interface TrampBrandProps {
  compact?: boolean;
  className?: string;
  as?: "div" | "h1";
}

export function TrampBrand({
  compact = false,
  className = "",
  as: BrandElement = "div",
}: TrampBrandProps) {
  const classes = [
    "tramp-brand",
    compact ? "tramp-brand-compact" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <BrandElement className={classes}>
      <span className="brand-wordmark">TRAMP</span>
      <span className="brand-expansion">TRAVEL AMPLIFIER</span>
    </BrandElement>
  );
}
