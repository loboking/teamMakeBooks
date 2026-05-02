import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "Pretendard",
          "-apple-system",
          "BlinkMacSystemFont",
          "sans-serif",
        ],
        serif: ["Georgia", "serif"],
      },
      colors: {
        brand: {
          DEFAULT: "#6C3CE1",
          dark: "#5A2FCC",
        },
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};

export default config;
