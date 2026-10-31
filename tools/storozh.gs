// Сторож замен (скрипт Гугла на почте расписания, script.google.com). Каждые 5 минут смотрит страницу
// замен на сайте техникума и, если там появилось новое распоряжение (или поменялось старое), сразу
// запускает обновление сайта расписания на GitHub (update.yml). Обычная проверка раз в час остаётся
// запасной. Ключ GitHub — в «Свойствах скрипта» (GH_TOKEN), в коде его нет.
//
// Как поставить: новый проект → вставить этот файл → сохранить → в «Настройках проекта» добавить
// свойство скрипта GH_TOKEN (ключ GitHub с правом «Actions: чтение и запись» только для репозитория
// raspisanie-utgt.github.io) → выбрать функцию ustanovit → «Выполнить» → разрешить доступ.

var PAGE = "https://utgt-pgups.ru/ochnoe-zaochnoe-otdelenie/58-zamena-zanyatij.html";
var WORKFLOW = "https://api.github.com/repos/raspisanie-utgt/raspisanie-utgt.github.io/actions/workflows/update.yml/dispatches";

// «Отпечаток» страницы: картинки распоряжений (адрес и содержимое — учебная часть может перезалить
// исправленную картинку под тем же именем) и текст статьи (без календаря событий, он меняется сам)
function otpechatok_() {
  var r = UrlFetchApp.fetch(PAGE, { muteHttpExceptions: true, followRedirects: true });
  if (r.getResponseCode() !== 200) return null;
  var html = r.getContentText("UTF-8");
  var start = html.indexOf("com-content-article__body");
  if (start < 0) return null;
  var end = html.indexOf("Предстоящие события", start);
  var body = html.substring(start, end > 0 ? end : start + 30000);
  var imgs = (body.match(/<img[^>]+src="[^"#]+/g) || []).filter(function (s) { return s.indexOf("new_2026") < 0; });
  var text = body.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
  var base = PAGE.replace(/^(https?:\/\/[^\/]+).*$/, "$1");
  var sums = imgs.map(function (s) {
    var src = s.replace(/^.*src="/, ""), url = /^https?:/.test(src) ? src : base + (src.charAt(0) === "/" ? "" : "/") + src;
    try {
      var r = UrlFetchApp.fetch(url, { muteHttpExceptions: true });
      return r.getResponseCode() === 200 ? Utilities.base64Encode(Utilities.computeDigest(Utilities.DigestAlgorithm.MD5, r.getContent())) : "нет";
    } catch (e) { return "нет"; }
  });
  return Utilities.base64Encode(Utilities.computeDigest(Utilities.DigestAlgorithm.MD5,
    imgs.join("|") + "|" + sums.join("|") + "|" + text, Utilities.Charset.UTF_8));
}

function storozh() {
  var print;
  try { print = otpechatok_(); } catch (e) { console.log("сайт техникума не ответил: " + e); return; }
  if (!print) { console.log("страница замен не открылась или поменялась вёрстка"); return; }
  var props = PropertiesService.getScriptProperties();
  if (props.getProperty("print") === print) return;
  console.log("на странице замен что-то изменилось — запускаю обновление сайта");
  if (zapustit_()) props.setProperty("print", print);   // не получилось — повторим через 5 минут
}

function zapustit_() {
  var token = PropertiesService.getScriptProperties().getProperty("GH_TOKEN");
  if (!token) { console.log("нет свойства скрипта GH_TOKEN"); return false; }
  var r = UrlFetchApp.fetch(WORKFLOW, {
    method: "post", contentType: "application/json", payload: JSON.stringify({ ref: "main" }),
    headers: { Authorization: "Bearer " + token, Accept: "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28" },
    muteHttpExceptions: true
  });
  var ok = r.getResponseCode() === 204;
  console.log(ok ? "обновление сайта запущено" : "GitHub не принял запуск: " + r.getResponseCode() + " " + r.getContentText());
  return ok;
}

// Запустить один раз вручную: ставит проверку каждые 5 минут и сразу проверяет ключ (запускает обновление)
function ustanovit() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === "storozh") ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger("storozh").timeBased().everyMinutes(5).create();
  PropertiesService.getScriptProperties().deleteProperty("print");
  storozh();
  if (!PropertiesService.getScriptProperties().getProperty("print")) {
    throw new Error("Проверка каждые 5 минут поставлена, но обновление сайта не запустилось — см. журнал выше");
  }
  console.log("Готово: сторож проверяет страницу замен каждые 5 минут");
}
