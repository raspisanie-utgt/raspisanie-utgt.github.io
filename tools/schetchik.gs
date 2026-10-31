// Счётчик сайта расписания (скрипт Гугла, script.google.com); адрес — COUNTER в site/app.js.
// Раз в день каждое устройство присылает «+1». Никаких адресов, меток и имён — только число
// устройств за день; адрес в интернете скрипту Гугл не передаёт вовсе.
// Накрутка: адрес открыт всем, поэтому не больше LIMIT «+1» в минуту (больше — не считаем),
// и запрос не ждёт очереди дольше 2 с. Числу всё равно стоит верить «на глаз».
//
// Как поставить (с компьютера):
// 1. script.google.com → «Создать проект» → вставить этот файл целиком → сохранить.
// 2. В списке функций выбрать proverka → «Выполнить» → «Предоставить доступ» → почта →
//    «Дополнительные настройки» → «Перейти на страницу…» → «Разрешить».
//    На Диске появится таблица «Счётчик сайта расписания УТЖТ».
// 3. «Начать развертывание» → «Новое развертывание» → тип «Веб-приложение»;
//    «Запуск от имени»: Я; «У кого есть доступ»: Все → «Начать развертывание».
// 4. Скопировать адрес, оканчивающийся на /exec, — его встроить в сайт.

var LIMIT = 30;  // «+1» в минуту — с запасом: живых устройств за день несколько десятков

function doGet(e) {
  var cache = CacheService.getScriptCache(), key = "m" + Math.floor(Date.now() / 60000);
  var n = Number(cache.get(key) || 0) + 1;
  cache.put(key, String(n), 120);
  if (n > LIMIT) return ContentService.createTextOutput("ok");
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(2000)) return ContentService.createTextOutput("ok");
  try {
    var sh = list_();
    var day = Utilities.formatDate(new Date(), "Europe/Moscow", "yyyy-MM-dd");
    var app = e && e.parameter && e.parameter.app === "1" ? 1 : 0;
    var last = sh.getLastRow();
    if (last > 1 && String(sh.getRange(last, 1).getDisplayValue()) === day) {
      var r = sh.getRange(last, 2, 1, 2), v = r.getValues()[0];
      r.setValues([[Number(v[0]) + 1, Number(v[1]) + app]]);
    } else {
      sh.appendRow([day, 1, app]);
    }
  } finally {
    lock.releaseLock();
  }
  return ContentService.createTextOutput("ok");
}

function list_() {
  var props = PropertiesService.getScriptProperties();
  var id = props.getProperty("table");
  if (id) return SpreadsheetApp.openById(id).getSheets()[0];
  var ss = SpreadsheetApp.create("Счётчик сайта расписания УТЖТ");
  var sh = ss.getSheets()[0];
  sh.getRange("A:A").setNumberFormat("@");
  sh.appendRow(["День", "Устройств", "Из них как приложение"]);
  sh.setFrozenRows(1);
  props.setProperty("table", ss.getId());
  return sh;
}

// Запустить один раз вручную: создаёт таблицу и спрашивает разрешения
function proverka() { list_(); }
