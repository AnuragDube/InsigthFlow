import { useState } from "react";
import { BASE_CURRENCY, CURRENCIES, validRate } from "../lib/currency";
import type { CurrencyPreference, DisplayCurrency } from "../lib/currency";

export function CurrencyPicker({ value, onApply }: {
  value: CurrencyPreference;
  onApply: (value: CurrencyPreference) => void;
}) {
  const [code, setCode] = useState(value.code);
  const [rate, setRate] = useState(value.code === "GBP" ? "" : String(value.rate));
  return (
    <details>
      <summary>Display currency ({value.code}{value.code !== "GBP" ? ", manual rate" : ""})</summary>
      <form className="toolbar" onSubmit={(event) => {
        event.preventDefault();
        if (code === "GBP") onApply(BASE_CURRENCY);
        else if (validRate(Number(rate))) onApply({ code, rate: Number(rate) });
        event.currentTarget.closest("details")?.removeAttribute("open");
      }}>
        <label className="field">
          Display currency
          <select value={code} onChange={(event) => {
            const next = event.target.value as DisplayCurrency;
            setCode(next);
            setRate(next === value.code && next !== "GBP" ? String(value.rate) : "");
          }}>
            {CURRENCIES.map((option) => <option key={option}>{option}</option>)}
          </select>
        </label>
        {code !== "GBP" && (
          <label className="field">
            1 GBP in {code}
            <input aria-label={`1 GBP in ${code}`} type="number" inputMode="decimal" min="0.000001" max="1000000" step="any" required value={rate} onChange={(event) => setRate(event.target.value)} />
          </label>
        )}
        <button type="submit" className="btn" disabled={code !== "GBP" && !validRate(Number(rate))}>
          Apply currency
        </button>
      </form>
      <p className="hint">Enter your own rate. The same rate applies to every displayed date.</p>
    </details>
  );
}
