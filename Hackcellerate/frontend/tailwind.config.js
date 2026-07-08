/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{html,ts}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#EEF4FB",
          100: "#DCE9F5",
          200: "#B4CFE9",
          300: "#8AB4DC",
          400: "#5F94CB",
          500: "#3A75B8",
          600: "#255C99",
          700: "#1B4675",
          800: "#132F52",
          900: "#0B1E38",
        },
        ink: {
          50: "#F7F9FC",
          100: "#EEF2F8",
          200: "#DDE4EE",
          300: "#C3CDDD",
          400: "#94A2B8",
          500: "#64748B",
          600: "#475569",
          700: "#334155",
          800: "#1F2937",
          900: "#0F172A",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "Helvetica",
          "Arial",
          "sans-serif",
        ],
        mono: ["JetBrains Mono", "Consolas", "Menlo", "monospace"],
      },
      boxShadow: {
        panel: "0 1px 2px 0 rgba(15, 23, 42, 0.04), 0 1px 3px 0 rgba(15, 23, 42, 0.06)",
        pop: "0 8px 24px -8px rgba(15, 23, 42, 0.18)",
      },
    },
  },
  plugins: [],
};
