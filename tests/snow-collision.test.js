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
  assert.ok(b.count <= 30);
  assert.ok(b.frameMs >= 40);
});

const {createField,impact,melt,maxHeight} = require('../site/appearance-renderer');
test('local snowdrift accumulates where flakes land instead of a full-width stripe', () => {
  const field=createField();
  impact(field, .5, 2);
  assert.ok(field[24] > 1.9);
  assert.equal(field[0], 0);
  assert.equal(field[48], 0);
  assert.ok(field.filter(x=>x>.01).length < 12);
});
test('independent cards have independent accumulation maps', () => {
  const a=createField(),b=createField();
  impact(a,.25,2);impact(b,.75,1);
  assert.equal(a[40],0);
  assert.equal(b[10],0);
  assert.notDeepEqual(a,b);
});
test('non-falling snow gradually melts and then disappears', () => {
  const f=createField();impact(f,.4,6);
  const initial=maxHeight(f);
  melt(f,5);
  assert.ok(maxHeight(f)>0 && maxHeight(f)<initial);
  melt(f,100);
  assert.equal(maxHeight(f),0);
});
test('non-enumerable DOMRect-style properties still collide via explicit geometry', () => {
  const c={left:20,right:320,top:100,width:300,viewportHeight:800};
  assert.equal(collision(150,99,103,c,{left:12,right:12}),true);
  assert.equal(collision(21,99,103,c,{left:12,right:12}),false);
});
