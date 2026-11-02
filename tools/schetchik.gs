// Счётчик сайта расписания (скрипт Гугла, script.google.com); адрес — COUNTER в site/app.js.
// Раз в день каждое устройство присылает «+1» (и вид: телефон / компьютер / планшет). Никаких адресов,
// меток и имён — только числа за день; адрес в интернете скрипту Гугл не передаёт вовсе.
// Обновить код (с компьютера): вставить файл → сохранить → «Начать развертывание» → «Управление развертываниями» →
// карандаш → «Версия: новая версия» → «Начать развертывание» (адрес /exec остаётся прежним).
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
    var q = (e && e.parameter) || {}, app = q.app === "1" ? 1 : 0;
    // вид устройства: t — телефон, k — компьютер, p — планшет (старые версии сайта не присылают — не считаем)
    var dev = [q.dev === "t" ? 1 : 0, q.dev === "k" ? 1 : 0, q.dev === "p" ? 1 : 0];
    shapka_(sh);
    var last = sh.getLastRow();
    if (last > 1 && String(sh.getRange(last, 1).getDisplayValue()) === day) {
      var r = sh.getRange(last, 2, 1, 5), v = r.getValues()[0];
      r.setValues([[Number(v[0]) + 1, Number(v[1]) + app, Number(v[2] || 0) + dev[0], Number(v[3] || 0) + dev[1], Number(v[4] || 0) + dev[2]]]);
    } else {
      sh.appendRow([day, 1, app].concat(dev));
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
  sh.appendRow(SHAPKA);
  sh.setFrozenRows(1);
  props.setProperty("table", ss.getId());
  return sh;
}

var SHAPKA = ["День", "Устройств", "Из них как приложение", "Телефонов", "Компьютеров", "Планшетов"];
// в таблице, созданной до разбивки по видам устройств, дописать заголовки новых столбцов
function shapka_(sh) {
  if (String(sh.getRange(1, 4).getValue()) !== SHAPKA[3]) sh.getRange(1, 1, 1, SHAPKA.length).setValues([SHAPKA]);
}

// Запустить один раз вручную: создаёт таблицу и спрашивает разрешения
function proverka() { list_(); }
