/**
 * Stub-DOM harness for src/ui/ribbon/ribbon.js.
 *
 * ribbon.js is a browser IIFE with no dependencies, so it can be exercised in
 * Node against a minimal DOM stand-in. Every case prints a line:
 *
 *   OK <case>   /   FAIL <case>: <reason>
 *
 * and the process exits non-zero if any case fails. The Python test asserts
 * both the exit code and that every expected case name is present, so a
 * harness that silently stops running its cases cannot pass.
 */
'use strict';

const assert = require('assert');
const path = require('path');

const RIBBON_JS = path.resolve(__dirname, '..', '..', 'src', 'ui', 'ribbon', 'ribbon.js');
const SVG_NS = 'http://www.w3.org/2000/svg';

// Controls applied by the fake createElementNS.
let nextPathLen = 0;
let lenThrows = false;

function makeEl(tag) {
  const el = {
    tagName: tag,
    ns: null,
    attrs: {},
    children: [],
    cssVars: {},
    style: {
      setProperty(name, value) {
        el.cssVars[name] = String(value);
      },
    },
    classList: {
      classes: [],
      add(name) {
        el.classList.classes.push(name);
      },
    },
    setAttribute(name, value) {
      el.attrs[name] = String(value);
    },
    getAttribute(name) {
      return Object.prototype.hasOwnProperty.call(el.attrs, name) ? el.attrs[name] : null;
    },
    appendChild(child) {
      el.children.push(child);
      return child;
    },
    querySelector(selector) {
      // Only 'svg.ribbon-svg' is ever queried by ribbon.js.
      const cls = selector.replace(/^[a-z]+\./, '');
      return el.children.find((child) => child.attrs.class === cls) || null;
    },
    getTotalLength() {
      if (lenThrows) throw new Error('getTotalLength not available in this env');
      return el.measuredLen;
    },
  };
  return el;
}

function makeWrap(ribbonJson) {
  const wrap = makeEl('div');
  wrap.setAttribute('data-ribbon', ribbonJson);
  return wrap;
}

const listeners = {};
let currentWraps = [];

global.document = {
  // 'loading' means ribbon.js must defer init until DOMContentLoaded, which
  // lets each case drive init explicitly.
  readyState: 'loading',
  addEventListener(name, fn) {
    listeners[name] = fn;
  },
  querySelectorAll() {
    return currentWraps;
  },
  createElementNS(ns, tag) {
    const el = makeEl(tag);
    el.ns = ns;
    if (tag === 'path') el.measuredLen = nextPathLen;
    return el;
  },
};

const ribbon = require(RIBBON_JS);

function spec(overrides) {
  const ribbonDef = {
    id: 'hero',
    path: { points: [[20, 80], [180, 20]] },
    style: { stroke: '#7c5cff', width: 3 },
  };
  if (overrides) Object.assign(ribbonDef, overrides);
  return JSON.stringify({ version: 'ribbon.v1', kind: 'ribbon', ribbons: [ribbonDef] });
}

function run(wrap, len) {
  nextPathLen = len === undefined ? 123.5 : len;
  currentWraps = [wrap];
  ribbon.init(global.document);
  return wrap;
}

function svgOf(wrap) {
  const svg = wrap.children[0];
  assert.ok(svg, 'expected an <svg> to be appended to the wrap');
  return svg;
}

function pathOf(wrap) {
  const path = svgOf(wrap).children[0];
  assert.ok(path, 'expected a <path> inside the <svg>');
  return path;
}

const cases = [
  ['defers_init_until_dom_ready', () => {
    assert.strictEqual(typeof listeners['DOMContentLoaded'], 'function',
      'readyState=loading must defer init via DOMContentLoaded');
    assert.strictEqual(typeof ribbon.init, 'function', 'init must be exported');
    assert.strictEqual(typeof ribbon.easing, 'function', 'easing must be exported');
  }],

  ['easing_math_matches_css_keywords', () => {
    assert.strictEqual(ribbon.easing(0.5, 'linear'), 0.5);
    assert.strictEqual(ribbon.easing(0.5, 'ease-in'), 0.25);
    assert.strictEqual(ribbon.easing(0.5, 'ease-out'), 0.75);
    assert.strictEqual(ribbon.easing(0.5, 'ease-in-out'), 0.5);
    assert.strictEqual(ribbon.easing(0.25, 'ease-in-out'), 0.125);
    // Unknown easing falls through to identity rather than throwing.
    assert.strictEqual(ribbon.easing(0.5, 'bounce'), 0.5);
    assert.strictEqual(ribbon.easing(0.5, undefined), 0.5);
  }],

  ['creates_svg_in_the_svg_namespace', () => {
    const svg = svgOf(run(makeWrap(spec())));
    assert.strictEqual(svg.ns, SVG_NS, 'svg must be created in the SVG namespace');
    assert.strictEqual(svg.attrs.class, 'ribbon-svg');
    assert.strictEqual(svg.attrs.viewBox, '0 0 560 120');
    assert.strictEqual(svg.attrs.role, 'img');
    assert.strictEqual(svg.attrs['aria-label'], 'ribbon');
  }],

  ['path_geometry_builds_move_and_line_commands', () => {
    const open = pathOf(run(makeWrap(spec())));
    // Segments are joined with a space, so the command letter does not abut
    // the previous coordinate pair: 'M20 80 L180 20'.
    assert.strictEqual(open.attrs.d, 'M20 80 L180 20');
    assert.strictEqual(open.ns, SVG_NS, 'path must be created in the SVG namespace');
    assert.strictEqual(open.attrs.class, 'ribbon-path');
  }],

  ['closed_path_appends_z', () => {
    const closed = pathOf(run(makeWrap(spec({ path: { points: [[0, 0], [10, 10]], closed: true } }))));
    assert.strictEqual(closed.attrs.d, 'M0 0 L10 10 Z');
  }],

  ['stroke_attributes_are_copied_from_the_spec', () => {
    const path = pathOf(run(makeWrap(spec({ style: { stroke: '#abcdef', width: 0.5, opacity: 0.4 } }))));
    assert.strictEqual(path.attrs.stroke, '#abcdef');
    assert.strictEqual(path.attrs['stroke-width'], '0.5');
    assert.strictEqual(path.attrs.opacity, '0.4');
  }],

  ['opacity_is_omitted_when_absent', () => {
    const path = pathOf(run(makeWrap(spec())));
    assert.strictEqual(path.getAttribute('opacity'), null,
      'opacity must not be set when the spec omits it');
  }],

  ['css_variables_come_from_the_measured_length_and_spec', () => {
    const path = pathOf(run(makeWrap(spec({
      animation: { duration_ms: 1200, easing: 'ease-out', loop: true, direction: 'alternate' },
    })), 123.5));
    assert.strictEqual(path.cssVars['--len'], '123.5', '--len must be the measured path length');
    assert.strictEqual(path.cssVars['--dur'], '1200ms');
    assert.strictEqual(path.cssVars['--easing'], 'ease-out');
    assert.ok(path.classList.classes.includes('animate'), '.animate class must be added');
    assert.strictEqual(path.attrs.class, 'ribbon-path',
      'classList.add must not replace the class attribute');
  }],

  ['animation_defaults_are_applied_when_the_block_is_missing', () => {
    const path = pathOf(run(makeWrap(spec()), 50));
    assert.strictEqual(path.cssVars['--dur'], '1800ms');
    assert.strictEqual(path.cssVars['--easing'], 'ease-in-out');
    assert.strictEqual(path.cssVars['--len'], '50');
    assert.ok(path.classList.classes.includes('animate'));
  }],

  ['malformed_json_is_skipped_without_throwing', () => {
    const wrap = run(makeWrap('{"version": "ribbon.v1"'));
    assert.deepStrictEqual(wrap.children, [], 'a malformed spec must not create an svg');
  }],

  ['empty_ribbon_list_is_skipped', () => {
    const wrap = run(makeWrap(JSON.stringify({ version: 'ribbon.v1', kind: 'ribbon', ribbons: [] })));
    assert.deepStrictEqual(wrap.children, [], 'an empty ribbon list must not create an svg');
  }],

  ['missing_get_total_length_degrades_without_animate', () => {
    lenThrows = true;
    try {
      const wrap = run(makeWrap(spec()));
      assert.strictEqual(svgOf(wrap).children.length, 1,
        'the path must still be appended when length measurement is unavailable');
      const path = pathOf(wrap);
      assert.strictEqual(path.cssVars['--len'], undefined,
        '--len cannot be measured, so it must be left unset');
      assert.ok(!path.classList.classes.includes('animate'),
        'animation must not be enabled when the length is unknown');
    } finally {
      lenThrows = false;
    }
  }],

  ['existing_svg_is_reused_not_duplicated', () => {
    const wrap = makeWrap(spec());
    run(wrap);
    run(wrap);
    assert.strictEqual(wrap.children.length, 1, 'a second init must reuse the existing svg');
  }],
];

let failed = 0;
for (const [name, fn] of cases) {
  try {
    fn();
    console.log('OK ' + name);
  } catch (error) {
    failed += 1;
    console.log('FAIL ' + name + ': ' + error.message);
  }
}

process.exit(failed === 0 ? 0 : 1);
