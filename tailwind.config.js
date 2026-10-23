module.exports = {
  content: ["./templates/**/*.html"],
  theme: {
    extend: {
      colors: {
        background: "#faf8ff",
        "on-surface": "#131b2e",
        "on-surface-variant": "#434656",
        primary: "#0042cb",
        "primary-container": "#1b59f8",
        "surface-container": "#eaedff",
        "surface-container-low": "#f2f3ff",
        "surface-container-lowest": "#ffffff",
        "outline-variant": "#c3c5d9",
        "tertiary-fixed": "#7ffc97",
        "on-tertiary-fixed": "#002109"
      },
      fontFamily: {
        sans: ["Plus Jakarta Sans", "ui-sans-serif", "system-ui", "sans-serif"]
      },
      boxShadow: {
        card: "0 18px 45px rgb(19 27 46 / 8%)",
        button: "0 3px 10px rgb(19 27 46 / 7%)",
        "button-hover": "0 7px 18px rgb(19 27 46 / 10%)"
      }
    }
  },
  plugins: []
};
