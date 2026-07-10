/*  MY-Card — 3D Tilt Effect
 *  Attach interactive parallax + shine to any element with [data-mc-tilt].
 *  Zero dependency. Respects prefers-reduced-motion.
 *
 *  Usage in HTML:
 *    <div class="mc-tilt" data-mc-tilt data-mc-tilt-max="12">
 *      <div class="mc-tilt__shine"></div>
 *      ...content...
 *    </div>
 */
(function () {
  'use strict';

  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduce) return;

  function init(el) {
    var max = parseFloat(el.dataset.mcTiltMax || '10');
    var shine = el.querySelector('.mc-tilt__shine');
    var rect;

    function onEnter() {
      rect = el.getBoundingClientRect();
      if (shine) el.style.setProperty('--mc-shine', '1');
    }

    function onMove(e) {
      if (!rect) rect = el.getBoundingClientRect();
      var x = (e.clientX - rect.left) / rect.width;   // 0..1
      var y = (e.clientY - rect.top) / rect.height;   // 0..1
      var rx = (0.5 - y) * (max * 2);
      var ry = (x - 0.5) * (max * 2);
      el.style.setProperty('--mc-rx', rx.toFixed(2) + 'deg');
      el.style.setProperty('--mc-ry', ry.toFixed(2) + 'deg');
      if (shine) {
        el.style.setProperty('--mc-mx', (x * 100).toFixed(1) + '%');
        el.style.setProperty('--mc-my', (y * 100).toFixed(1) + '%');
      }
    }

    function onLeave() {
      el.style.setProperty('--mc-rx', '0deg');
      el.style.setProperty('--mc-ry', '0deg');
      if (shine) el.style.setProperty('--mc-shine', '0');
      rect = null;
    }

    el.addEventListener('mouseenter', onEnter);
    el.addEventListener('mousemove', onMove);
    el.addEventListener('mouseleave', onLeave);
  }

  function boot() {
    document.querySelectorAll('[data-mc-tilt]').forEach(init);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
