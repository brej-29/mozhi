/* Apply the saved theme before styles paint. */
try {
  const theme = localStorage.getItem("mozhi-theme");
  if (theme === "light" || theme === "dark")
    document.documentElement.dataset.theme = theme;
} catch {
  /* The system theme works when storage is unavailable. */
}
