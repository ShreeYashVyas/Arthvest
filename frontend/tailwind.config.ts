import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        canvas: "#080B10",
        panel: "#10151D",
        line: "#252D39",
        muted: "#8793A5",
        accent: "#B7F36B",
      },
    },
  },
  plugins: [],
};

export default config;
