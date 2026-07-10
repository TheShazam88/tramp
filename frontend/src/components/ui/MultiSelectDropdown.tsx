import { useMemo, useState } from "react";

import type { SelectOption } from "@/data/aviationOptions";

export function MultiSelectDropdown({
  id,
  label,
  options,
  selectedValues,
  onChange,
  disabled = false,
  helperText,
  otherPlaceholder = "Add another code",
}: {
  id: string;
  label: string;
  options: SelectOption[];
  selectedValues: string[];
  onChange: (values: string[]) => void;
  disabled?: boolean;
  helperText?: string;
  otherPlaceholder?: string;
}) {
  const [otherValue, setOtherValue] = useState("");
  const optionValues = useMemo(() => new Set(options.map((option) => option.value)), [options]);
  const customValues = selectedValues.filter((value) => !optionValues.has(value));
  const selectedLabels = selectedValues.map(
    (value) => options.find((option) => option.value === value)?.label ?? value,
  );

  const summary =
    selectedValues.length === 0
      ? "All included by default"
      : selectedLabels.length <= 2
        ? selectedLabels.join(", ")
        : `${selectedLabels[0]}, ${selectedLabels[1]} + ${selectedLabels.length - 2} more`;

  return (
    <div className="field-stack">
      <label htmlFor={id}>{label}</label>
      <details className="multi-select" open={!selectedValues.length}>
        <summary className="multi-select-summary">{summary}</summary>
        <div className="multi-select-panel">
          {selectedValues.length > 0 ? (
            <div className="toolbar-row">
              <p className="helper-copy">{selectedValues.length} currently selected.</p>
              <button
                type="button"
                className="button button-ghost"
                disabled={disabled}
                onClick={() => onChange([])}
              >
                Clear all
              </button>
            </div>
          ) : null}
          <div className="multi-select-options">
            {options.map((option) => {
              const checked = selectedValues.includes(option.value);
              return (
                <label key={option.value} className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={checked}
                    disabled={disabled}
                    onChange={(event) => {
                      if (event.target.checked) {
                        onChange([...selectedValues, option.value]);
                        return;
                      }
                      onChange(selectedValues.filter((value) => value !== option.value));
                    }}
                  />
                  <span>{option.label}</span>
                </label>
              );
            })}
          </div>

          <div className="multi-select-other">
            <p className="field-label">Other</p>
            <div className="multi-select-other-row">
              <input
                id={id}
                className="text-input"
                value={otherValue}
                onChange={(event) => setOtherValue(event.target.value.toUpperCase())}
                placeholder={otherPlaceholder}
                disabled={disabled}
              />
              <button
                type="button"
                className="button button-secondary"
                disabled={disabled || !otherValue.trim()}
                onClick={() => {
                  const nextValue = otherValue.trim().toUpperCase();
                  if (!nextValue || selectedValues.includes(nextValue)) {
                    setOtherValue("");
                    return;
                  }
                  onChange([...selectedValues, nextValue]);
                  setOtherValue("");
                }}
              >
                Add
              </button>
            </div>
            {customValues.length > 0 ? (
              <div className="pill-row">
                {customValues.map((value) => (
                  <button
                    key={value}
                    type="button"
                    className="pill pill-button pill-selected"
                    disabled={disabled}
                    onClick={() => onChange(selectedValues.filter((item) => item !== value))}
                  >
                    {value} x
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      </details>
      {helperText ? <p className="helper-copy">{helperText}</p> : null}
    </div>
  );
}
