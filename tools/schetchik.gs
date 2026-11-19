// Счётчик: только дневные суммы. Исходный User-Agent, IP, ID и выбранная группа не записываются.
// Google как принимающий сервер видит сетевые сведения запроса; скрипт не даёт автору доступа к ним.
// Сначала сохранить фактический старый исходник, затем обновить существующее развёртывание /exec.
// Вручную выполнить podgotovitOtchet(): резервная копия листа, новые колонки, отчёт и диаграммы.
// Адрес /exec и свойство table сохранить. Новый проект/таблицу вместо существующих не создавать.
var LIMIT = 30;
var SHAPKA = ['День', 'Устройств', 'Из них как приложение', 'Телефонов', 'Компьютеров', 'Планшетов',
  'С новой разбивкой', 'Android', 'iOS / iPadOS', 'Windows', 'macOS', 'Linux', 'ChromeOS', 'Другая / неизвестная ОС',
  'Chrome', 'Safari', 'Яндекс Браузер', 'Edge', 'Firefox', 'Opera', 'Samsung Internet', 'Другой / неизвестный браузер'];
var OS = ['a', 'i', 'w', 'm', 'l', 'c', 'o'];
var BR = ['c', 'a', 'y', 'e', 'f', 'o', 's', 'x'];

function values_(q) {
  q = q || {};
  var v2 = q.v === '2';
  var os = OS.indexOf(q.os), br = BR.indexOf(q.br);
  if (os < 0) os = OS.length - 1;
  if (br < 0) br = BR.length - 1;
  return [1, q.app === '1' ? 1 : 0, q.dev === 't' ? 1 : 0, q.dev === 'k' ? 1 : 0,
    q.dev === 'p' ? 1 : 0, v2 ? 1 : 0].concat(
      OS.map(function (_, i) { return v2 && i === os ? 1 : 0; }),
      BR.map(function (_, i) { return v2 && i === br ? 1 : 0; }));
}

function doGet(e) {
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(2000)) return ContentService.createTextOutput('ok');
  try {
    // Limit accounting must also be inside the lock: concurrent requests otherwise lose increments.
    var cache = CacheService.getScriptCache(), key = 'm' + Math.floor(Date.now() / 60000);
    var n = Number(cache.get(key) || 0) + 1;
    cache.put(key, String(n), 120);
    if (n > LIMIT) return ContentService.createTextOutput('ok');
    var sh = list_();
    shapka_(sh);
    var day = Utilities.formatDate(new Date(), 'Europe/Moscow', 'yyyy-MM-dd');
    var add = values_((e && e.parameter) || {}), last = sh.getLastRow();
    if (last > 1 && String(sh.getRange(last, 1).getDisplayValue()) === day) {
      var r = sh.getRange(last, 2, 1, add.length), old = r.getValues()[0];
      r.setValues([add.map(function (v, i) { return Number(old[i] || 0) + v; })]);
    } else {
      // Old blank categories mean 'not collected'; never backfill historical categories with zeroes.
      var row = [day].concat(add);
      if (!e || !e.parameter || e.parameter.v !== '2') row = row.slice(0, 6);
      sh.getRange(last + 1, 1).setNumberFormat('@');
      sh.appendRow(row);
    }
  } finally { lock.releaseLock(); }
  return ContentService.createTextOutput('ok');
}

function list_() {
  var props = PropertiesService.getScriptProperties(), id = props.getProperty('table');
  if (!id) throw new Error('Нет свойства table: укажите существующую таблицу; автоматически новая не создаётся.');
  var ss = SpreadsheetApp.openById(id), sheetId = props.getProperty('counterSheetId');
  var sheets = ss.getSheets(), sh;
  if (sheetId !== null) {
    sh = sheets.filter(function (s) { return String(s.getSheetId()) === sheetId; })[0];
    if (!sh) throw new Error('Исходный лист счётчика не найден.');
  } else {
    // Legacy code used the first sheet. Pin it before a report/backup can change tab ordering.
    sh = sheets[0];
    validate_(sh);
    props.setProperty('counterSheetId', String(sh.getSheetId()));
  }
  return sh;
}

function validate_(sh) {
  var width = Math.max(sh.getLastColumn(), 3);
  if (width > SHAPKA.length) throw new Error('Неожиданные дополнительные колонки — нужна проверка таблицы.');
  var head = sh.getRange(1, 1, 1, width).getValues()[0];
  head.forEach(function (v, i) {
    if ((i < 3 || v !== '') && v !== SHAPKA[i]) throw new Error('Неожиданный заголовок в колонке ' + (i + 1));
  });
}

function shapka_(sh) {
  validate_(sh);
  if (sh.getMaxColumns() < SHAPKA.length) sh.insertColumnsAfter(sh.getMaxColumns(), SHAPKA.length - sh.getMaxColumns());
  var old = sh.getRange(1, 1, 1, SHAPKA.length).getValues()[0];
  if (old.join('|') !== SHAPKA.join('|')) {
    backup_(sh);
    sh.getRange(1, 1, 1, SHAPKA.length).setValues([SHAPKA]);
  }
}

function backup_(sh) {
  var props = PropertiesService.getScriptProperties(), id = props.getProperty('statsV2BackupSheetId');
  if (id) {
    if (!sh.getParent().getSheets().some(function (s) { return String(s.getSheetId()) === id; })) {
      throw new Error('Резервный лист удалён: проверьте сохранность копии перед продолжением.');
    }
    return;
  }
  var backup = sh.copyTo(sh.getParent());
  backup.setName('Резерв до статистики ' + Utilities.formatDate(new Date(), 'Europe/Moscow', 'yyyy-MM-dd HH-mm-ss'));
  props.setProperty('statsV2BackupSheetId', String(backup.getSheetId()));
}

// Run once in the existing project; no triggers are created or replaced.
function podgotovitOtchet() {
  var lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    var sh = list_(), ss = sh.getParent(), props = PropertiesService.getScriptProperties();
    var report = ss.getSheetByName('Статистика устройств');
    if (report && !props.getProperty('statsReportSheetId') && report.getRange(40, 1).getDisplayValue() === 'UTGT_STATS_V2_REPORT') props.setProperty('statsReportSheetId', String(report.getSheetId()));
    if (report && props.getProperty('statsReportSheetId') !== String(report.getSheetId())) {
      throw new Error('Лист «Статистика устройств» уже существует и не принадлежит обновлению.');
    }
    if (ss.getSpreadsheetTimeZone() !== 'Europe/Moscow') throw new Error('Часовой пояс таблицы отличается от Europe/Moscow; настройки не изменены.');
    backup_(sh);
    shapka_(sh);
    sh.setFrozenRows(1);
    sh.getRange(1, 1, 1, SHAPKA.length).setFontWeight('bold').setBackground('#e7f0ed');
    sh.getRange(1, 2).setNote('Приблизительные дневные отметки браузеров. Это не точное число людей или физических устройств.');
    sh.getRange(1, 7).setNote('Покрытие новой разбивкой. Старые строки не содержат истории ОС и браузеров.');
    if (!report) {
      report = ss.insertSheet('Статистика устройств');
      props.setProperty('statsReportSheetId', String(report.getSheetId()));
    }
    var separator = /^(ru|de|fr|it|es|pt|pl|uk|nl|tr|cs|da|fi|sv|no|hu|ro|bg|el|sk|sl|lt|lv|et)(_|$)/i.test(ss.getSpreadsheetLocale()) ? ';' : ',';
    function localFormulas(rows) { return rows.map(function (r) { return r.map(function (f) { return separator === ';' ? f.replace(/,/g, ';') : f; }); }); }
    // Only the dedicated, owned report is regenerated. Source and backup are never cleared.
    report.clear();
    report.getCharts().forEach(function (chart) { report.removeChart(chart); });
    var src = "'" + sh.getName().replace(/'/g, "''") + "'!";
    // Normalise dates in the report only: historical native dates and future ISO text both work.
    var bound = sh.getMaxRows();
    if (report.getMaxRows() < bound) report.insertRowsAfter(report.getMaxRows(), bound - report.getMaxRows());
    if (report.getMaxColumns() < 27) report.insertColumnsAfter(report.getMaxColumns(), 27 - report.getMaxColumns());
    var normalDates = [];
    for (var n = 2; n <= bound; n++) {
      var cell = src + 'A' + n;
      normalDates.push(['=IF(' + cell + '="","",IF(ISNUMBER(' + cell + '),INT(' + cell + '),DATE(VALUE(LEFT(' + cell + ',4)),VALUE(MID(' + cell + ',6,2)),VALUE(RIGHT(' + cell + ',2)))))']);
    }
    report.getRange(1, 27).setValue('Дата для расчёта — исходные даты не изменяются');
    report.getRange(2, 27, bound - 1, 1).setFormulas(localFormulas(normalDates));
    report.hideColumns(27);
    function sum(col, period) {
      var r = src + col + '2:' + col + bound;
      if (period === 3) return 'SUM(' + r + ')';
      var start = ['TODAY()', 'TODAY()-WEEKDAY(TODAY(),2)+1', 'DATE(YEAR(TODAY()),MONTH(TODAY()),1)'][period];
      return 'SUMIFS(' + r + ',AA2:AA' + bound + ',">="&(' + start + '),AA2:AA' + bound + ',"<"&(TODAY()+1))';
    }
    report.getRange('A1').setValue('Использование сайта расписания УТЖТ');
    report.getRange('A2').setValue('Дневные отметки браузеров, не уникальные люди. Неделя — с понедельника, месяц — с первого числа.');
    report.getRange('A3').setValue('Старые даты без ОС/браузера не восстановить. Распознавание категорий приблизительное; PWA — режим запуска.');
    report.getRange('A5:E5').setValues([['Период', 'Отметок', 'Как приложение', 'В браузере', 'С новой разбивкой']]);
    ['Сегодня', 'Текущая неделя', 'Текущий месяц', 'Всё время'].forEach(function (label, i) {
      var row = 6 + i;
      report.getRange(row, 1).setValue(label);
      report.getRange(row, 2, 1, 4).setFormulas(localFormulas([['=' + sum('B', i), '=' + sum('C', i),
        '=B' + row + '-C' + row, '=' + sum('G', i)]]));
    });
    function section(row, title, labels, cols) {
      report.getRange(row, 1, 1, 5).setValues([[title, 'Сегодня', 'Неделя', 'Месяц', 'Всё время']]);
      labels.forEach(function (label, j) {
        report.getRange(row + j + 1, 1).setValue(label);
        report.getRange(row + j + 1, 2, 1, 4).setFormulas(localFormulas([[0, 1, 2, 3].map(function (i) {
          return '=' + (cols[j] === '?' ? sum('B', i) + '-(' + ['D', 'E', 'F'].map(function (c) { return sum(c, i); }).join('+') + ')' : sum(cols[j], i));
        })]));
      });
    }
    section(12, 'Тип устройства', ['Телефон', 'Компьютер', 'Планшет', 'Не определён / старая версия'], ['D', 'E', 'F', '?']);
    section(19, 'Операционная система (новая разбивка)', SHAPKA.slice(7, 14), ['H', 'I', 'J', 'K', 'L', 'M', 'N']);
    section(29, 'Браузер (новая разбивка)', SHAPKA.slice(14), ['O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V']);
    [[12, 4, 'Устройства — все дневные отметки'], [19, 7, 'ОС — только новая разбивка'], [29, 8, 'Браузеры — только новая разбивка']].forEach(function (c, i) {
      report.insertChart(report.newChart().setChartType(Charts.ChartType.BAR)
        .addRange(report.getRange(c[0], 1, c[1] + 1, 1)).addRange(report.getRange(c[0], 5, c[1] + 1, 1))
        .setNumHeaders(1).setPosition(5 + 16 * i, 7, 0, 0).setOption('title', c[2])
        .setOption('legend', { position: 'none' }).setOption('width', 620).setOption('height', 300).build());
    });
    report.getRange(40, 1).setValue('UTGT_STATS_V2_REPORT');
    report.getRange('A1').setFontSize(18).setFontWeight('bold');
    [5, 12, 19, 29].forEach(function (r) { report.getRange(r, 1, 1, 5).setFontWeight('bold').setBackground('#e7f0ed'); });
    report.setRowHeights(5, 1, 46);
    report.setColumnWidth(1, 310); report.setColumnWidths(2, 4, 130);
    report.getRange('A2:E3').setWrap(true); report.setRowHeights(2, 2, 45);
    report.getRange('B6:E37').setNumberFormat('0'); report.setFrozenRows(5);
    SpreadsheetApp.flush();
    Logger.log('Отчёт обновлён. Исходные данные и резервная копия сохранены.');
  } finally { lock.releaseLock(); }
}

function proverka() { var sh = list_(); validate_(sh); }
