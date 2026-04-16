/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Dark theme surfaces
        surface: {
          0: "#0d0f12",
          1: "#13161b",
          2: "#1a1e25",
          3: "#222730",
          4: "#2a3040",
        },
        // Brand accent: indigo/blue
        accent: {
          DEFAULT: "#4f7cff",
          hover: "#6b93ff",
          muted: "#2a3f80",
        },
        // Status colors
        green: {
          profit: "#22c55e",
          muted: "#16a34a",
        },
        red: {
          loss: "#ef4444",
          muted: "#dc2626",
        },
        // Paper (blue) vs live (green)
        paper: "#3b82f6",
        live: "#22c55e",
        // Text
        text: {
          primary: "#f0f2f5",
          secondary: "#8b9ab0",
          tertiary: "#4a5568",
        },
        border: "#1e2433",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Menlo", "monospace"],
      },
      fontSize: {
        "2xs": ["0.65rem", { lineHeight: "1rem" }],
      },
      boxShadow: {
        card: "0 1px 3px 0 rgba(0,0,0,0.4), 0 1px 2px -1px rgba(0,0,0,0.4)",
        "card-lg": "0 4px 16px 0 rgba(0,0,0,0.5)",
      },
    },
  },
  plugins: [],
};
