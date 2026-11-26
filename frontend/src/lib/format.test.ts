import { formatChange, formatDateRange, formatExact, formatValue } from "./format";

describe("formatValue", () => {
  it("abbreviates large money amounts", () => {
    expect(formatValue(19701685.49, "GBP")).toBe("£19.7M");
    expect(formatValue(719656.34, "GBP")).toBe("£720K");
    expect(formatValue(18982029.15, "GBP")).toBe("£19.0M");
  });
  it("keeps pence for small amounts", () => {
    expect(formatValue(140.445, "GBP")).toBe("£140.45");
  });
  it("formats counts with separators", () => {
    expect(formatValue(1015074, "count")).toBe("1,015,074");
  });
  it("formats ratios as percentages", () => {
    expect(formatValue(0.25, "ratio")).toBe("25.0%");
  });
  it("shows a dash when there is no data", () => {
    expect(formatValue(null, "GBP")).toBe("—");
  });
  it("converts money with the manual rate and preserves counts and ratios", () => {
    const currency = { code: "INR", rate: 2 } as const;
    expect(formatValue(2, "GBP", currency)).toMatch(/^INR\s4\.00$/);
    expect(formatExact(-2, "GBP", currency)).toMatch(/^-INR\s4\.00$/);
    expect(formatValue(2000, "count", currency)).toBe("2,000");
    expect(formatValue(0.25, "ratio", currency)).toBe("25.0%");
  });
});

describe("formatChange", () => {
  it("signs the change against the previous period", () => {
    expect(formatChange(0.1234)).toBe("+12.3%");
    expect(formatChange(-0.433)).toBe("−43.3%");
  });
  it("shows a dash when there is nothing to compare with", () => {
    expect(formatChange(null)).toBe("—");
  });
});

describe("formatDateRange", () => {
  it("writes ranges the way people say them", () => {
    expect(formatDateRange("2009-12-01", "2011-12-09")).toBe("1 Dec 2009 to 9 Dec 2011");
    expect(formatDateRange("2010-12-04", "2010-12-04")).toBe("4 Dec 2010");
  });
});
