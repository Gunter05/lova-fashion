/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        cream:      { DEFAULT: '#FAF8F5', dark: '#F2EDE6' },
        terracotta: { DEFAULT: '#D95D39', light: '#E8785A', dark: '#B54A2E' },
        sage:       { DEFAULT: '#4E6E58', light: '#6A8F76', dark: '#3A5242' },
      },
    },
  },
  plugins: [],
}
