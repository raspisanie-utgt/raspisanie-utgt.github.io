// Only broad categories leave the browser. No raw User-Agent, versions or identifiers.
(function (root) {
  "use strict";
  function categories(nav, screen, match) {
    nav = nav || {}; screen = screen || {};
    var ua = nav.userAgent || "";
    var ipad = /iPad/i.test(ua) || (/Macintosh/i.test(ua) && nav.maxTouchPoints > 1);
    var os = /Android/i.test(ua) ? "a" : /iPhone|iPod/i.test(ua) || ipad ? "i" :
      /Windows/i.test(ua) ? "w" : /CrOS/i.test(ua) ? "c" :
      /Macintosh|Mac OS X/i.test(ua) ? "m" : /Linux/i.test(ua) ? "l" : "o";
    var browser = /YaBrowser\//i.test(ua) ? "y" : /Edg(?:A|iOS)?\//i.test(ua) ? "e" :
      /OPR\/|Opera|OPiOS\//i.test(ua) ? "o" : /SamsungBrowser\//i.test(ua) ? "s" :
      /Firefox\/|FxiOS\//i.test(ua) ? "f" : /Chrome\/|CriOS\//i.test(ua) ? "c" :
      /Version\/.*Safari\//i.test(ua) ? "a" : "x";
    // Embedded browsers and known alternate Chromium browsers are not labelled Chrome.
    if (/; wv\)|\bFBAN\b|\bFBAV\b|Instagram|GSA\/|HuaweiBrowser\/|Vivaldi\//i.test(ua)) browser = "x";
    var device;
    if (ipad || /Tablet/i.test(ua) || (/Android/i.test(ua) && !/Mobi/i.test(ua))) device = "p";
    else if (/Mobi|iPhone|iPod/i.test(ua)) device = "t";
    else if (/Windows|Macintosh|CrOS|X11|Linux/i.test(ua)) device = "k";
    else if (match && match("(pointer: coarse)").matches && !match("(any-pointer: fine)").matches) {
      var edge = Math.min(screen.width || 0, screen.height || 0);
      device = edge > 0 ? (edge < 600 ? "t" : "p") : "u";
    } else device = "u";
    return { dev: device, os: os, br: browser };
  }
  function query(nav, screen, match, app) {
    var c = categories(nav, screen, match);
    return "v=2&app=" + (app ? "1" : "0") + "&dev=" + c.dev + "&os=" + c.os + "&br=" + c.br;
  }
  var api = { categories: categories, query: query };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.VisitStats = api;
})(typeof window !== "undefined" ? window : this);
