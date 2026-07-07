import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./index.html",
    "./src/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Paleta inspirada en Win11 dark + accent azul
        bg: {
          DEFAULT: "#0F0F12",
          surface: "#1A1A1F",
          elevated: "#22222A",
          hover: "#2A2A33",
        },
        border: {
          DEFAULT: "#2E2E38",
          strong: "#3F3F46",
        },
        text: {
          DEFAULT: "#E4E4E7",
          muted: "#A1A1AA",
          subtle: "#71717A",
        },
        accent: {
          DEFAULT: "#0078D4",
          hover: "#106EBE",
          subtle: "rgba(0, 120, 212, 0.1)",
        },
        success: "#22C55E",
        warn: "#F59E0B",
        danger: "#EF4444",
        info: "#3B82F6",
      },
      fontFamily: {
        sans: [
          "Inter",
          "Segoe UI",
          "system-ui",
          "-apple-system",
          "sans-serif",
        ],
        mono: ["JetBrains Mono", "Consolas", "monospace"],
      },
      animation: {
        "fade-in": "fadeIn 200ms ease-out",
        "slide-up": "slideUp 250ms ease-out",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
