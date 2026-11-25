// What each analysis asks the user for. The panel builds its form from this.

export interface RoleSpec {
  key: string;
  label: string;
  multiple?: boolean;
  optional?: boolean;
  hint?: string;
  /** Only show this role when an option has a given value. */
  when?: { option: string; values: string[] };
  /** Pick from the second table's columns instead of the first's. */
  table?: "b";
}

export interface OptionSpec {
  key: string;
  label: string;
  type: "number" | "select" | "checkbox" | "text" | "multi";
  default?: number | string | boolean | string[] | null;
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
  /** Table tools: send every column, and write the output as a new data table. 2 = needs a second table. */
  tables?: 1 | 2;
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
  ...tableTools(),
];

function tableTools(): AnalysisSpec[] {
  const G = "Tables";
  const keyed = (opt: string, values: string[]): RoleSpec[] => [
    { key: "key", label: "Match rows on, first table", multiple: true, when: { option: opt, values } },
    { key: "key_b", label: "Matching columns, second table", multiple: true, optional: true, table: "b", when: { option: opt, values }, hint: "only if the names differ; paired in column order" },
  ];
  return [
    {
      id: "summary",
      label: "Summary",
      group: G,
      tables: 1,
      description: "One row per group with counts and statistics of the columns you choose.",
      roles: [
        { key: "group", label: "Group by", multiple: true, optional: true },
        { key: "y", label: "Statistics for", multiple: true, optional: true },
      ],
      options: [
        {
          key: "stats",
          label: "Statistics",
          type: "multi",
          default: ["n", "mean", "std", "min", "max"],
          choices: [
            { value: "n", label: "N" },
            { value: "n_missing", label: "N missing" },
            { value: "mean", label: "Mean" },
            { value: "std", label: "Std dev" },
            { value: "min", label: "Min" },
            { value: "max", label: "Max" },
            { value: "sum", label: "Sum" },
            { value: "median", label: "Median" },
          ],
        },
      ],
    },
    {
      id: "subset",
      label: "Subset",
      group: G,
      tables: 1,
      description: "Keep the rows that meet a condition, a random sample of rows, and the columns you choose.",
      roles: [
        { key: "keep", label: "Columns to keep", multiple: true, optional: true, hint: "none = all" },
        { key: "where", label: "Row condition on", optional: true },
      ],
      options: [
        {
          key: "op",
          label: "Condition",
          type: "select",
          default: "eq",
          choices: [
            { value: "eq", label: "equals" },
            { value: "ne", label: "does not equal" },
            { value: "lt", label: "is less than" },
            { value: "le", label: "is at most" },
            { value: "gt", label: "is greater than" },
            { value: "ge", label: "is at least" },
            { value: "contains", label: "contains" },
            { value: "not_contains", label: "does not contain" },
            { value: "missing", label: "is missing" },
            { value: "not_missing", label: "is not missing" },
          ],
        },
        { key: "value", label: "Value", type: "text", default: "", when: { option: "op", values: ["eq", "ne", "lt", "le", "gt", "ge", "contains", "not_contains"] } },
        {
          key: "sample",
          label: "Rows",
          type: "select",
          default: "all",
          choices: [
            { value: "all", label: "All matching rows" },
            { value: "first_n", label: "First N rows" },
            { value: "random_n", label: "Random sample of N rows" },
            { value: "random_fraction", label: "Random fraction of rows" },
          ],
        },
        { key: "count", label: "N", type: "number", default: 10, min: 1, step: 1, when: { option: "sample", values: ["first_n", "random_n"] } },
        { key: "fraction", label: "Fraction (0 to 1)", type: "number", default: 0.5, min: 0, max: 1, step: 0.05, when: { option: "sample", values: ["random_fraction"] } },
        { key: "seed", label: "Random seed (optional, repeats the sample)", type: "number", default: null, step: 1, when: { option: "sample", values: ["random_n", "random_fraction"] } },
      ],
    },
    {
      id: "sort",
      label: "Sort",
      group: G,
      tables: 1,
      description: "Order the rows by up to three columns. Empty cells go last.",
      roles: [
        { key: "by", label: "Sort by" },
        { key: "by2", label: "Then by", optional: true },
        { key: "by3", label: "Then by", optional: true },
      ],
      options: [
        { key: "desc", label: "First column descending", type: "checkbox", default: false },
        { key: "desc2", label: "Second column descending", type: "checkbox", default: false },
        { key: "desc3", label: "Third column descending", type: "checkbox", default: false },
      ],
    },
    {
      id: "stack",
      label: "Stack",
      group: G,
      tables: 1,
      description: "Wide to long: several columns become one data column plus a label column naming where each value came from.",
      roles: [{ key: "stack", label: "Columns to stack", multiple: true }],
      options: [
        { key: "data_name", label: "Name of the new data column", type: "text", default: "Data" },
        { key: "label_name", label: "Name of the new label column", type: "text", default: "Label" },
        { key: "drop_missing", label: "Leave out empty values", type: "checkbox", default: false },
      ],
    },
    {
      id: "split",
      label: "Split",
      group: G,
      tables: 1,
      description: "Long to wide: each value of the split-by column becomes a new column holding the split values.",
      roles: [
        { key: "split", label: "Values to split", multiple: true },
        { key: "by", label: "Split by (its values name the new columns)" },
        { key: "group", label: "Group rows by", multiple: true, optional: true, hint: "one output row per group" },
      ],
      options: [],
    },
    {
      id: "transpose",
      label: "Transpose",
      group: G,
      tables: 1,
      description: "Rows become columns and columns become rows.",
      roles: [
        { key: "columns", label: "Columns to transpose", multiple: true, optional: true, hint: "none = all" },
        { key: "label", label: "Names for the new columns from", optional: true },
      ],
      options: [],
    },
    {
      id: "join",
      label: "Join",
      group: G,
      tables: 2,
      description: "Put the columns of two tables side by side, matching rows on key columns or by row number.",
      roles: keyed("how", ["inner", "left", "right", "outer"]),
      options: [
        {
          key: "how",
          label: "Rows to keep",
          type: "select",
          default: "inner",
          choices: [
            { value: "inner", label: "Only rows that match" },
            { value: "left", label: "All rows of the first table" },
            { value: "right", label: "All rows of the second table" },
            { value: "outer", label: "All rows of both tables" },
            { value: "row", label: "Match by row number" },
          ],
        },
      ],
    },
    {
      id: "update",
      label: "Update",
      group: G,
      tables: 2,
      description: "Replace values in the first table with values from matching rows of the second. Columns are matched by name.",
      roles: keyed("match", ["key"]),
      options: [
        {
          key: "match",
          label: "Match rows",
          type: "select",
          default: "key",
          choices: [
            { value: "key", label: "On key columns" },
            { value: "row", label: "By row number" },
          ],
        },
        { key: "ignore_missing", label: "Keep the old value where the second table is empty", type: "checkbox", default: true },
        { key: "add_columns", label: "Add new columns from the second table", type: "checkbox", default: false },
      ],
    },
    {
      id: "concatenate",
      label: "Concatenate",
      group: G,
      tables: 2,
      description: "Append the rows of the second table below the first. Columns are matched by name; new ones are added.",
      roles: [],
      options: [{ key: "source_column", label: "Add a column naming the source table", type: "checkbox", default: true }],
    },
    {
      id: "missing_pattern",
      label: "Missing data pattern",
      group: G,
      tables: 1,
      description: "Which combinations of columns are empty, and how often.",
      roles: [{ key: "columns", label: "Columns", multiple: true, optional: true, hint: "none = all" }],
      options: [],
    },
    {
      id: "compare",
      label: "Compare tables",
      group: G,
      tables: 2,
      description: "Columns, rows and cell values that differ between two tables.",
      roles: [
        { key: "key", label: "Match rows on, first table", multiple: true, optional: true, hint: "none = by row number" },
        { key: "key_b", label: "Matching columns, second table", multiple: true, optional: true, table: "b", hint: "only if the names differ" },
      ],
      options: [],
    },
    {
      id: "anonymize",
      label: "Anonymize",
      group: G,
      tables: 1,
      description: "Replace text with coded labels, rescale numbers and rename columns, so data can be shared.",
      roles: [{ key: "columns", label: "Columns to anonymize", multiple: true, optional: true, hint: "none = all" }],
      options: [
        { key: "rename", label: "Rename columns (C1, C2, ...)", type: "checkbox", default: true },
        {
          key: "numeric",
          label: "Numeric columns",
          type: "select",
          default: "rescale",
          choices: [
            { value: "rescale", label: "Rescale (keeps relationships)" },
            { value: "keep", label: "Keep values" },
            { value: "text", label: "Replace with coded labels" },
          ],
        },
        { key: "seed", label: "Random seed (optional)", type: "number", default: null, step: 1 },
        { key: "include_key", label: "Also produce the key to reverse it", type: "checkbox", default: false },
      ],
    },
  ];
}

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
