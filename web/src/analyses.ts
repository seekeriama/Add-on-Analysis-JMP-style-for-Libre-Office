// What each analysis asks the user for. The panel builds its form from this.

export interface RoleSpec {
  key: string;
  label: string;
  multiple?: boolean;
  optional?: boolean;
  hint?: string;
  /** Only show this role when an option has a given value. */
  when?: { option: string; values: string[] };
}

export interface OptionSpec {
  key: string;
  label: string;
  type: "number" | "select" | "checkbox";
  default?: number | string | boolean | null;
  choices?: { value: string; label: string }[];
  step?: number;
  min?: number;
  max?: number;
  when?: { option: string; values: string[] };
}

export interface AnalysisSpec {
  id: string;
  label: string;
  group: string;
  description: string;
  roles: RoleSpec[];
  options: OptionSpec[];
  needsData?: boolean;
}

const confidence: OptionSpec = { key: "confidence", label: "Confidence level", type: "number", default: 0.95, step: 0.01, min: 0.5, max: 0.999 };

export const ANALYSES: AnalysisSpec[] = [
  {
    id: "distribution",
    label: "Distribution",
    group: "Explore",
    description: "Histogram, box plot, quantiles, summary statistics and normality tests for each column.",
    roles: [{ key: "y", label: "Y, columns", multiple: true }],
    options: [confidence],
  },
  {
    id: "fit_y_by_x",
    label: "Fit Y by X",
    group: "Explore",
    description:
      "Numeric Y and X: line fit. Numeric Y, categorical X: one-way ANOVA with Tukey HSD. Both categorical: contingency table.",
    roles: [
      { key: "y", label: "Y, response" },
      { key: "x", label: "X, factor" },
    ],
    options: [confidence],
  },
  {
    id: "fit_model",
    label: "Multiple regression",
    group: "Model",
    description: "Least-squares model with several X columns, effect tests, VIF and residual plots.",
    roles: [
      { key: "y", label: "Y, response" },
      { key: "x", label: "X, model terms", multiple: true },
    ],
    options: [confidence],
  },
  {
    id: "decision_tree",
    label: "Decision tree",
    group: "Model",
    description: "Splits the rows into groups that best predict Y. Classification for categorical Y, regression for numeric Y.",
    roles: [
      { key: "y", label: "Y, response" },
      { key: "x", label: "X, predictors", multiple: true },
    ],
    options: [
      { key: "max_depth", label: "Maximum depth", type: "number", default: 3, min: 1, max: 10, step: 1 },
      { key: "min_leaf", label: "Minimum rows per leaf", type: "number", default: 5, min: 1, step: 1 },
      { key: "validation", label: "Validation share (0 to 0.4)", type: "number", default: 0, min: 0, max: 0.4, step: 0.05 },
    ],
  },
  {
    id: "control_chart",
    label: "Control chart",
    group: "Quality",
    description: "Shewhart charts with Western Electric rules 1 to 4 flagged in red.",
    roles: [
      { key: "y", label: "Measurement (or defectives / defects)" },
      { key: "subgroup", label: "Subgroup ID", optional: true, when: { option: "chart", values: ["xbar_r", "xbar_s"] }, hint: "or set a subgroup size" },
      { key: "n", label: "Sample size", when: { option: "chart", values: ["p"] } },
    ],
    options: [
      {
        key: "chart",
        label: "Chart type",
        type: "select",
        default: "imr",
        choices: [
          { value: "imr", label: "Individuals and moving range (I-MR)" },
          { value: "xbar_r", label: "X̄ and R" },
          { value: "xbar_s", label: "X̄ and S" },
          { value: "p", label: "p (proportion defective)" },
          { value: "c", label: "c (defects per unit)" },
        ],
      },
      { key: "subgroup_size", label: "Subgroup size (if no ID column)", type: "number", default: 5, min: 2, max: 25, step: 1, when: { option: "chart", values: ["xbar_r", "xbar_s"] } },
    ],
  },
  {
    id: "capability",
    label: "Process capability",
    group: "Quality",
    description: "Cp, Cpk, Pp, Ppk and expected PPM against specification limits.",
    roles: [
      { key: "y", label: "Measurement" },
      { key: "subgroup", label: "Subgroup ID", optional: true, hint: "otherwise moving range" },
    ],
    options: [
      { key: "lsl", label: "Lower spec limit (LSL)", type: "number", default: null },
      { key: "target", label: "Target", type: "number", default: null },
      { key: "usl", label: "Upper spec limit (USL)", type: "number", default: null },
      { key: "subgroup_size", label: "Subgroup size (if no ID column)", type: "number", default: null, min: 2, max: 25, step: 1 },
      confidence,
    ],
  },
  {
    id: "gauge_rr",
    label: "Gauge R&R",
    group: "Quality",
    description: "Crossed measurement system study by the ANOVA method, with AIAG acceptance guidance.",
    roles: [
      { key: "y", label: "Measurement" },
      { key: "part", label: "Part" },
      { key: "operator", label: "Operator" },
    ],
    options: [
      { key: "tolerance", label: "Tolerance (USL − LSL), optional", type: "number", default: null },
      { key: "study_multiplier", label: "Study variation multiplier", type: "number", default: 6, step: 0.15 },
    ],
  },
  {
    id: "doe_design",
    label: "Create two-level design",
    group: "Design of experiments",
    description: "Full or fractional two-level factorial run sheet, exported to a new sheet for you to fill in.",
    roles: [],
    options: [
      { key: "runs", label: "Runs", type: "select", default: "" },
      { key: "center_points", label: "Center points", type: "number", default: 0, min: 0, step: 1 },
      { key: "replicates", label: "Replicates", type: "number", default: 1, min: 1, step: 1 },
      { key: "randomize", label: "Randomize run order", type: "checkbox", default: true },
    ],
    needsData: false,
  },
  {
    id: "doe_analyze",
    label: "Analyze screening design",
    group: "Design of experiments",
    description: "Effects, Pareto and half-normal plots for a two-level design. Factor columns may hold actual or coded settings.",
    roles: [
      { key: "y", label: "Response" },
      { key: "x", label: "Factors", multiple: true },
    ],
    options: [{ key: "interactions", label: "Include two-factor interactions", type: "checkbox", default: true }],
  },
];

/** Run counts for a two-level design with k factors (mirrors core/cellstat/doe.py). */
export function runChoices(k: number): { value: string; label: string }[] {
  const frac: Record<number, [number, string][]> = {
    3: [[4, "III"]],
    4: [[8, "IV"]],
    5: [[8, "III"], [16, "V"]],
    6: [[8, "III"], [16, "IV"], [32, "VI"]],
    7: [[8, "III"], [16, "IV"], [32, "IV"], [64, "VII"]],
  };
  const out = (frac[k] ?? []).map(([r, res]) => ({ value: String(r), label: `${r} runs, fractional (resolution ${res})` }));
  if (k >= 2 && k <= 7) out.push({ value: String(2 ** k), label: `${2 ** k} runs, full factorial` });
  return out;
}
