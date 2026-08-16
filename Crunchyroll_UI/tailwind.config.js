/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        crbase: "#0B0B10", // Deep Dark Void
        crpanel: "#151520", // Elevated Dark Panel
        crpurple: "#7E22CE", // Deep Purple
        crviolet: "#8B5CF6", // Neon Violet Accent
        crsilver: "#C0C0C0", // Sleek Silver Text/Borders
      },
    },
  },
  plugins: [],
};
