/**
 * ribbon.js — progressive enhancement for ribbon.css
 * Reads ribbon.spec.json (or inline data-attrs), measures path length, sets CSS vars,
 * and drives dash animation with rAF so it stays deterministic across reflows.
 * Zero deps. Adds <svg> if none exists.
 */
(function () {
  'use strict';
  function easing(t, kind) {
    if (kind === 'ease-in') return t * t;
    if (kind === 'ease-out') return t * (2 - t);
    if (kind === 'ease-in-out') return t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
    return t;
  }
  function init(root) {
    root = root || document;
    var wraps = root.querySelectorAll('.ribbon-wrap[data-ribbon]');
    for (var i = 0; i < wraps.length; i++) {
      var wrap = wraps[i];
      var spec;
      try { spec = JSON.parse(wrap.getAttribute('data-ribbon')); } catch (e) { continue; }
      if (!spec || !spec.ribbons || !spec.ribbons.length) continue;
      var NS = 'http://www.w3.org/2000/svg';
      var svg = wrap.querySelector('svg.ribbon-svg');
      if (!svg) {
        svg = document.createElementNS(NS, 'svg');
        svg.setAttribute('class', 'ribbon-svg');
        svg.setAttribute('viewBox', '0 0 560 120');
        svg.setAttribute('role', 'img');
        svg.setAttribute('aria-label', 'ribbon');
        wrap.appendChild(svg);
      }
      for (var r = 0; r < spec.ribbons.length; r++) {
        var rib = spec.ribbons[r];
        var d = rib.path.points.map(function (pt, j) { return (j === 0 ? 'M' : 'L') + pt[0] + ' ' + pt[1]; }).join(' ');
        if (rib.path.closed) d += ' Z';
        var path = document.createElementNS(NS, 'path');
        path.setAttribute('class', 'ribbon-path');
        path.setAttribute('d', d);
        path.setAttribute('stroke', rib.style.stroke);
        path.setAttribute('stroke-width', rib.style.width);
        if (rib.style.opacity != null) path.setAttribute('opacity', rib.style.opacity);
        svg.appendChild(path);
        // measure + animate
        try {
          var len = path.getTotalLength();
          path.style.setProperty('--len', String(len));
          var dur = (rib.animation && rib.animation.duration_ms) || 1800;
          var ea = (rib.animation && rib.animation.easing) || 'ease-in-out';
          path.style.setProperty('--dur', dur + 'ms');
          path.style.setProperty('--easing', ea);
          path.classList.add('animate');
        } catch (e) { /* getTotalLength not in this env */ }
      }
    }
  }
  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { init(document); });
    else init(document);
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = { init: init, easing: easing };
})();
