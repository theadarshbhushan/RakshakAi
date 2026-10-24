/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        page: "#F6F5F1",
        sidebar: "#FBFAF7",
        card: "#FFFFFF",
        fill: {
          subtle: "#F1EFEA",
          active: "#ECEAE4",
        },
        border: {
          card: "#E5E2DB",
          input: "#DAD6CE",
          divider: "#EEECE7",
        },
        primary: {
          DEFAULT: "#1E5B4F",
          hover: "#17483E",
          tint: "#EEF5F2",
          "tint-strong": "#DCE7E2",
        },
        critical: {
          DEFAULT: "#C42B2B",
          danger: "#B3261E",
          tint: "#FBF1F0",
          border: "#EBCDC9",
        },
        status: {
          high: "#D9730D",
          "high-tint": "#FDF0E2",
          medium: "#C9A227",
          "medium-tint": "#FDF9EB",
          low: "#2F6FB5",
          "low-tint": "#EEF5FB",
          healthy: "#2E8B57",
          "healthy-tint": "#EEF7F2",
        },
        content: {
          primary: "#1F2023",
          body: "#34363B",
          secondary: "#5C5F66",
          muted: "#6B6E75",
        },
        video: {
          bg: "#24262B",
          activePerson: "#EDEBE6",
          person: "#B9B7B1",
          alertBox: "#F06A62",
        }
      },
      fontFamily: {
        sans: ['"DM Sans"', "sans-serif"],
        mono: ['"IBM Plex Mono"', "monospace"],
      },
      borderRadius: {
        card: "12px",
        btn: "8px",
        input: "9px",
      },
      boxShadow: {
        soft: "0 1px 2px 0 rgba(0, 0, 0, 0.04)",
      }
    },
  },
  plugins: [],
}
