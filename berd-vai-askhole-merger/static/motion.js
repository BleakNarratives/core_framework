(() => {
  const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
  let scheduled = false;

  const updateDepth = () => {
    const depth = motionQuery.matches ? 0 : Math.min(window.scrollY * 0.16, 180);
    document.body.dataset.scrollDepth = String(Math.round(depth / 30));
    scheduled = false;
  };

  const requestDepthUpdate = () => {
    if (!scheduled) {
      scheduled = true;
      window.requestAnimationFrame(updateDepth);
    }
  };

  window.addEventListener('scroll', requestDepthUpdate, { passive: true });
  window.addEventListener('resize', requestDepthUpdate, { passive: true });
  motionQuery.addEventListener?.('change', requestDepthUpdate);
  requestDepthUpdate();

  if (!motionQuery.matches) {
    document.querySelectorAll('.hero h1').forEach((headline) => {
      headline.classList.add('arrive');
    });
  }
})();
