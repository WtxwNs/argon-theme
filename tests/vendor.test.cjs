const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const { JSDOM } = require('jsdom');
const root = process.env.ARGON_VENDOR_ROOT || path.resolve(__dirname, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');

const jquery = read('assets/vendor/jquery/jquery.min.js');
const merged = read('assets/argon_js_merged.js');

test('standalone and merged jQuery assets use the same official release', () => {
  assert.match(jquery, /jQuery v3\.7\.1/);
  assert.ok(merged.startsWith('/* assets/vendor/jquery/jquery.min.js */\n' + jquery));
});

for (const bundle of ['standalone', 'merged']) {
  test(`${bundle} browser dependencies`, async (t) => {
    const dom = new JSDOM('<!doctype html><html><head></head><body></body></html>', {
      url: 'https://example.test/', runScripts: 'outside-only', pretendToBeVisual: true,
    });
    t.after(() => dom.window.close());
    const window = dom.window;
    if (bundle === 'merged') {
      window.eval(merged);
    } else {
      window.eval(jquery);
      window.eval(read('assets/vendor/popper/popper.min.js'));
      window.eval(read('assets/vendor/bootstrap/bootstrap.bundle.min.js'));
    }
    const $ = window.jQuery;
    await t.test('retains expected APIs and ordinary HTML handling', () => {
      assert.equal($.fn.jquery, '3.7.1');
      for (const api of ['ajax', 'parseHTML', 'extend']) assert.equal(typeof $[api], 'function');
      assert.equal(typeof $.fn.modal, 'function');
      assert.equal(typeof $.fn.tooltip, 'function');
      assert.equal($.fn.tooltip.Constructor.VERSION, '4.6.2');
      const target = $('<div>').appendTo('body');
      target.html('<p><strong>comment</strong></p>');
      assert.equal(target.find('strong').text(), 'comment');
      target.remove();
    });
    await t.test('does not rewrite self-closing HTML before DOM parsing', () => {
      const markup = '<div/><span title="<div />">text</span>';
      assert.equal($.htmlPrefilter(markup), markup);
    });
    await t.test('deep extension ignores prototype keys', () => {
      const input = JSON.parse('{"__proto__":{"polluted":true}}');
      const output = $.extend(true, {}, input);
      assert.equal(output.polluted, undefined);
      const polluted = window.Object.prototype.polluted;
      delete window.Object.prototype.polluted;
      delete Object.prototype.polluted;
      assert.equal(polluted, undefined);
    });
    await t.test('modal can open, dismiss and open again', () => {
      const modal = $('<div class="modal" tabindex="-1"><div class="modal-dialog"><div class="modal-content">content</div></div></div>').appendTo('body');
      modal.modal({ show: false });
      modal.modal('show'); assert.equal(modal.hasClass('show'), true);
      modal.modal('hide'); assert.equal(modal.hasClass('show'), false);
      modal.modal('show'); assert.equal(modal.hasClass('show'), true);
      modal.modal('hide'); modal.modal('dispose'); modal.remove();
    });
    if (bundle === 'merged') {
      await t.test('Tippy retains its separate Popper 2 integration', () => {
        assert.equal(typeof window.Popper.createPopper, 'function');
        const button = window.document.createElement('button');
        window.document.body.appendChild(button);
        const tip = window.tippy(button, { content: 'details', trigger: 'manual', animation: false });
        tip.show(); assert.equal(tip.state.isVisible, true);
        tip.hide(); assert.equal(tip.state.isVisible, false);
        tip.destroy(); button.remove();
      });
    }
    await t.test('tooltip still sanitizes its HTML content', () => {
      const button = $('<button title="">details</button>').appendTo('body');
      button.tooltip({ html: true, animation: false, title: '<b>details</b><script>invalid</script>' });
      button.tooltip('show');
      assert.equal(window.document.querySelector('.tooltip-inner b').textContent, 'details');
      assert.equal(window.document.querySelector('.tooltip-inner script'), null);
      button.tooltip('hide'); button.tooltip('dispose'); button.remove();
    });
  });
}
