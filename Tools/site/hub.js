(() => {
  const MULTS = [0.1, 0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 10];
  const slider = document.getElementById("xp-mult-slider");
  const label = document.getElementById("xp-mult-label");
  const link = document.getElementById("xp-download");
  if (!slider || !label || !link) return;

  function formatMult(m) {
    return Number.isInteger(m) ? String(m) : String(m);
  }

  function sync() {
    const idx = Number(slider.value) || 0;
    const m = MULTS[Math.min(Math.max(idx, 0), MULTS.length - 1)];
    const file = `xp_scale_${formatMult(m)}.zip`;
    label.textContent = `×${formatMult(m)}`;
    link.href = `./xp_scale/${file}`;
    link.setAttribute("download", file);
  }

  slider.addEventListener("input", sync);
  sync();
})();
