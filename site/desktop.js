// Раскладка для компьютера: сверху синяя полоса (часы, дата, группа, полоса дней, «до каникул»),
// ниже три столбца — выбранный день, следующий учебный день, справа замены, новости и остальное.
// Включается только на широком экране с мышью, поэтому на телефоне (даже повёрнутом) её не будет.
// На телефоне страница не меняется.
(function () {
  "use strict";
  // компьютер с мышью — от 1024 точек; большой планшет, повёрнутый горизонтально, — от 1100 (телефоны лёжа уже)
  var mq = window.matchMedia("(min-width: 1024px) and (hover: hover) and (pointer: fine), (min-width: 1100px) and (min-height: 700px)");
  var wrap = document.querySelector("main.wrap");
  var order = Array.prototype.slice.call(wrap.children); // исходный порядок — чтобы вернуть как было
  var day = document.getElementById("dayView");
  var images = document.getElementById("images");
  var bar, side, newsWasOpen = false;

  function on() {
    bar = document.createElement("div");
    bar.className = "desk-bar";
    var inner = document.createElement("div");
    inner.className = "desk-bar-in";
    inner.appendChild(wrap.querySelector(".top"));
    inner.appendChild(wrap.querySelector(".tabs"));
    bar.appendChild(inner);
    wrap.parentNode.insertBefore(bar, wrap);
    side = document.createElement("aside");
    side.className = "desk-side";
    side.appendChild(images);
    ["#tiles", "#news", "#whereD", "#useful", ".foot"].forEach(function (s) {
      var el = wrap.querySelector(s);
      if (el) side.appendChild(el);
    });
    wrap.appendChild(side);
    // места много — новости сразу открыты (на телефоне остаются свёрнутыми)
    var news = document.getElementById("news");
    newsWasOpen = news.open;
    news.open = true;
    document.documentElement.classList.add("desk");
    window.dispatchEvent(new Event("utgt-desk"));
  }

  function off() {
    document.documentElement.classList.remove("desk");
    document.getElementById("news").open = newsWasOpen;
    day.appendChild(images);
    order.forEach(function (el) { wrap.appendChild(el); });
    if (bar) bar.remove();
    if (side) side.remove();
    bar = side = null;
    window.dispatchEvent(new Event("utgt-desk"));
  }

  function apply() {
    var want = mq.matches;
    if (want && !bar) on();
    else if (!want && bar) off();
  }
  apply();
  if (mq.addEventListener) mq.addEventListener("change", apply);
  else if (mq.addListener) mq.addListener(apply);
})();
