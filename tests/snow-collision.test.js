const { test } = require('node:test');
const assert = require('node:assert/strict');
const { collision, budget } = require('../site/appearance-renderer');

const card = { left: 20, right: 320, top: 100, width: 300, height: 80 };
test('flakes hitting upper surface are caught only while falling', () => {
  assert.equal(collision(110, 98, 102, card, 16), true);
  assert.equal(collision(110, 102, 108, card, 16), false);
  assert.equal(collision(110, 85, 95, card, 16), false);
  assert.equal(collision(110, 110, 85, card, 16), false);
});
test('rounded corners and outside area do not accumulate snow', () => {
  assert.equal(collision(21, 98, 102, card, 16), false);
  assert.equal(collision(319, 98, 102, card, 16), false);
  assert.equal(collision(300, 98, 102, card, 16), true);
});
test('mobile animation has bounded pixel scale and flake count', () => {
  const b = budget(393, 851, 3.5, 4, 8);
  assert.equal(b.scale, 1);
  assert.ok(b.count <= 24);
  assert.ok(b.frameMs >= 40);
});
