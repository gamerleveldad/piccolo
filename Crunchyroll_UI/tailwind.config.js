/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        crbase: '#0B101E',    // Deep Void Background
        crpanel: '#1A233A',   // Elevated Card/Panel
        craqua: '#008E97',    // Neon Aqua Accents
        crorange: '#FC4C02',  // Vibrant Orange Highlights
      }
    },
  },
  plugins: [],
}