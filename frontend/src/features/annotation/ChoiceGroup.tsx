import { useId } from "react";
import { optionTone, type Tone } from "./presentation";
export function ChoiceGroup({
  label,
  field,
  value,
  options,
  onChange,
  disabled = false,
}: {
  label: string;
  field?: string;
  value: string;
  options: { value: string; label: string; tone?: Tone }[];
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  const name = useId();
  return (
    <div className="annotation-choice" role="radiogroup" aria-label={label} data-count={options.length}>
      {options.map((option) => (
        <label
          className={
            "annotation-option" + (value === option.value ? " selected" : "")
          }
          data-tone={option.tone ?? optionTone(field ?? "", option.value)}
          key={option.value}
        >
          <input
            type="radio"
            name={name}
            value={option.value}
            checked={value === option.value}
            disabled={disabled}
            onChange={() => onChange(option.value)}
          />
          <span><span>{option.label}</span><i className="choice-check" aria-hidden="true">✓</i></span>
        </label>
      ))}
    </div>
  );
}
