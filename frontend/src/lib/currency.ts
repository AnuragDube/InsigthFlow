import { createContext, useContext } from "react";

export const CURRENCIES = ["GBP", "USD", "EUR", "INR"] as const;
export type DisplayCurrency = typeof CURRENCIES[number];
export interface CurrencyPreference {
  code: DisplayCurrency;
  rate: number;
}

export const BASE_CURRENCY: CurrencyPreference = { code: "GBP", rate: 1 };
const STORAGE_KEY = "insightflow-display-currency";

export function validRate(rate: number): boolean {
  return Number.isFinite(rate) && rate >= 0.000001 && rate <= 1_000_000;
}

export function readCurrency(): CurrencyPreference {
  try {
    const saved = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "null");
    if (saved && CURRENCIES.includes(saved.code) && saved.code !== "GBP" &&
        typeof saved.rate === "number" && validRate(saved.rate)) return saved;
  } catch {
    // Display preferences are optional when browser storage is disabled.
  }
  return BASE_CURRENCY;
}

export function saveCurrency(preference: CurrencyPreference): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(preference));
  } catch {
    // The current page can still use the preference.
  }
}

export const CurrencyContext = createContext<CurrencyPreference>(BASE_CURRENCY);
export const useCurrency = () => useContext(CurrencyContext);
