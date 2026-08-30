/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // لوحة بيضاء: رمادي للبنية، ولون واحد للحالة الفعّالة
        ink: '#111111',
        muted: '#6b6b6b',
        line: '#e5e5e5',
        accent: '#111111',
      },
      fontFamily: {
        sans: ['Segoe UI', 'Tahoma', 'Noto Naskh Arabic', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
