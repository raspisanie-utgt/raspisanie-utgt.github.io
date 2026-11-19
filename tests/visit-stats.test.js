const test = require('node:test');
const assert = require('node:assert/strict');
const S = require('../site/visit-stats.js');
const cases = [
  ['Windows Chrome', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0.0.0 Safari/537.36', 'k', 'w', 'c'],
  ['Windows Edge', 'Mozilla/5.0 (Windows NT 10.0) Chrome/130 Safari/537.36 Edg/130.0', 'k', 'w', 'e'],
  ['Yandex Android', 'Mozilla/5.0 (Linux; Android 14) Chrome/130 Mobile Safari/537.36 YaBrowser/24.1', 't', 'a', 'y'],
  ['Android tablet', 'Mozilla/5.0 (Linux; Android 14) Chrome/130 Safari/537.36', 'p', 'a', 'c'],
  ['iPhone Safari', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Version/18.0 Mobile/15 Safari/604.1', 't', 'i', 'a'],
  ['iPhone Chrome', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) CriOS/130 Mobile/15 Safari/604.1', 't', 'i', 'c'],
  ['iPhone Firefox', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) FxiOS/130 Mobile/15 Safari/604.1', 't', 'i', 'f'],
  ['iPad', 'Mozilla/5.0 (iPad; CPU OS 18 like Mac OS X) Version/18.0 Mobile Safari/604.1', 'p', 'i', 'a'],
  ['Mac Safari', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) Version/18.0 Safari/605.1', 'k', 'm', 'a'],
  ['Linux Firefox', 'Mozilla/5.0 (X11; Linux x86_64) Firefox/130.0', 'k', 'l', 'f'],
  ['ChromeOS', 'Mozilla/5.0 (X11; CrOS x86_64 123) Chrome/130 Safari/537.36', 'k', 'c', 'c'],
  ['Samsung', 'Mozilla/5.0 (Linux; Android 14) SamsungBrowser/25 Chrome/130 Mobile Safari/537.36', 't', 'a', 's'],
  ['Opera', 'Mozilla/5.0 (Windows NT 10.0) Chrome/130 Safari/537.36 OPR/110', 'k', 'w', 'o'],
  ['WebView', 'Mozilla/5.0 (Linux; Android 14; wv) Chrome/130 Mobile Safari/537.36', 't', 'a', 'x'],
  ['Unknown', 'unrecognised client', 'u', 'o', 'x']
];
test('common browsers and OS; embedded and unknown clients are not invented', () => {
  for (const [label, ua, dev, os, br] of cases) {
    assert.deepEqual(S.categories({userAgent: ua}, {}, null), {dev, os, br}, label);
  }
  assert.deepEqual(S.categories({userAgent:'Macintosh Version/18 Safari/605',maxTouchPoints:5}, {}, null),
    {dev:'p',os:'i',br:'a'});
});
test('payload contains categories only, never UA, versions, IDs or group', () => {
  const q = S.query({userAgent:cases[0][1],language:'ru',platform:'Win32'}, {}, null, true);
  assert.equal(q, 'v=2&app=1&dev=k&os=w&br=c');
  assert.equal(S.query({}, {}, null, false), 'v=2&app=0&dev=u&os=o&br=x');
});
