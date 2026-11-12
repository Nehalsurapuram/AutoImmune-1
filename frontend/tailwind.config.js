/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        page: "var(--page)",
        surface: "var(--surface)",
        "surface-2": "var(--surface-2)",
        selected: "var(--selected)",
        line: "var(--line)",
        "line-strong": "var(--line-strong)",
        focus: "var(--focus)",
        text: {
          DEFAULT: "var(--text)",
          2: "var(--text-2)",
          3: "var(--text-3)",
          disabled: "var(--text-disabled)",
        },
        action: {
          DEFAULT: "var(--action)",
          hover: "var(--action-hover)",
          pressed: "var(--action-pressed)",
          disabled: "var(--action-disabled)",
        },
        "on-action": {
          DEFAULT: "var(--on-action)",
          disabled: "var(--on-action-disabled)",
        },
        control: {
          DEFAULT: "var(--control)",
          hover: "var(--control-hover)",
          pressed: "var(--control-pressed)",
        },
        lead: {
          DEFAULT: "var(--lead)",
          hover: "var(--lead-hover)",
          pressed: "var(--lead-pressed)",
          ink: "var(--lead-ink)",
          tint: "var(--lead-tint)",
          line: "var(--lead-line)",
        },
        "on-lead": {
          DEFAULT: "var(--on-lead)",
          2: "var(--on-lead-2)",
        },
        support: {
          DEFAULT: "var(--support)",
          hover: "var(--support-hover)",
          pressed: "var(--support-pressed)",
          ink: "var(--support-ink)",
          tint: "var(--support-tint)",
        },
        "on-support": "var(--on-support)",
        pop: {
          DEFAULT: "var(--pop)",
          ink: "var(--pop-ink)",
          tint: "var(--pop-tint)",
        },
        danger: {
          DEFAULT: "var(--danger)",
          hover: "var(--danger-hover)",
          pressed: "var(--danger-pressed)",
          ink: "var(--danger-ink)",
          tint: "var(--danger-tint)",
        },
        "on-danger": "var(--on-danger)",
        warning: {
          DEFAULT: "var(--warning)",
          hover: "var(--warning-hover)",
          pressed: "var(--warning-pressed)",
          ink: "var(--warning-ink)",
          tint: "var(--warning-tint)",
        },
        "on-warning": "var(--on-warning)",
        success: {
          DEFAULT: "var(--success)",
          hover: "var(--success-hover)",
          pressed: "var(--success-pressed)",
          ink: "var(--success-ink)",
          tint: "var(--success-tint)",
        },
        "on-success": "var(--on-success)",
        info: {
          DEFAULT: "var(--info)",
          hover: "var(--info-hover)",
          pressed: "var(--info-pressed)",
          ink: "var(--info-ink)",
          tint: "var(--info-tint)",
        },
        "on-info": "var(--on-info)",
        series: {
          1: "var(--series-1)",
          2: "var(--series-2)",
          3: "var(--series-3)",
          4: "var(--series-4)",
          5: "var(--series-5)",
          6: "var(--series-6)",
          muted: "var(--series-muted)",
        }
      },
      fontFamily: {
        sans: ['system-ui', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'sans-serif'],
        mono: ['ui-monospace', '"SF Mono"', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
      },
      boxShadow: {
        1: "var(--shadow-1)",
        2: "var(--shadow-2)",
      }
    },
  },
  plugins: [],
}
