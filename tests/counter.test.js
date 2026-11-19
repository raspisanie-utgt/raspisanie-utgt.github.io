const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
function fixture(rows) {
  const props = {table:'existing'}, sheets = [], charts = [];
  let nextId = 1;
  function col(s) { return [...s].reduce((n,c)=>n*26+c.charCodeAt(0)-64,0); }
  function sheet(name, data) {
    const sh = { name, id:nextId++, data:structuredClone(data), maxCols:26, charts:[], notes:[],
      getSheetId(){return this.id}, getName(){return this.name}, setName(n){this.name=n;return this},
      getParent(){return ss}, getLastRow(){return this.data.length},
      getLastColumn(){return Math.max(...this.data.map(r=>r.length),0)}, getMaxColumns(){return this.maxCols},
      insertColumnsAfter(_,n){this.maxCols+=n}, setFrozenRows(){},setColumnWidth(){},setColumnWidths(){},setRowHeights(){},
      appendRow(r){this.data.push([...r])}, copyTo(){return sheet('copy',this.data)},
      clear(){this.data=[];return this},getCharts(){return this.charts},removeChart(c){this.charts=this.charts.filter(x=>x!==c)},
      insertChart(c){this.charts.push(c);charts.push(c)},
      newChart(){const c={};for(const m of ['setChartType','addRange','setNumHeaders','setPosition','setOption']) c[m]=()=>c;c.build=()=>c;return c},
      getRange(row,c,nr=1,nc=1){
        if(typeof row==='string') {
          const m=/^([A-Z]+)(\d*)?(?::([A-Z]+)(\d*)?)?$/.exec(row);
          c=col(m[1]);nc=m[3]?col(m[3])-c+1:1;row=Number(m[2]||1);nr=m[4]?Number(m[4])-row+1:1;
        }
        const range={
          getValues(){return Array.from({length:nr},(_,i)=>Array.from({length:nc},(_,j)=>sh.data[row+i-1]?.[c+j-1]??''))},
          getDisplayValue(){return String(this.getValues()[0][0])},
          setValues(v){for(let i=0;i<nr;i++){sh.data[row+i-1]??=[];for(let j=0;j<nc;j++)sh.data[row+i-1][c+j-1]=v[i][j]}return this},
          setFormulas(v){return this.setValues(v)},setValue(v){return this.setValues([[v]])},
          setNote(v){sh.notes.push(v);return this}
        };
        for(const m of ['setFontWeight','setFontSize','setBackground','setNumberFormat','setWrap'])range[m]=()=>range;
        return range;
      }
    };sheets.push(sh);return sh;
  }
  const ss={getSheets:()=>sheets,getSheetByName:n=>sheets.find(s=>s.name===n),insertSheet:n=>sheet(n,[]),getSpreadsheetTimeZone:()=>ss.tz||'Europe/Moscow'};
  const source=sheet('Счётчик',rows);
  let released=0;
  const ctx={PropertiesService:{getScriptProperties:()=>({getProperty:k=>props[k]??null,setProperty:(k,v)=>{props[k]=v}})},
    SpreadsheetApp:{openById:id=>{assert.equal(id,'existing');return ss},flush(){}},
    LockService:{getScriptLock:()=>({tryLock:()=>true,waitLock(){},releaseLock(){released++}})},
    CacheService:{getScriptCache:()=>({get:()=>null,put(){}})},
    ContentService:{createTextOutput:s=>s},Utilities:{formatDate:()=> '2026-11-19'},Charts:{ChartType:{BAR:'bar'}},Logger:{log(){}}};
  vm.createContext(ctx);vm.runInContext(fs.readFileSync('tools/schetchik.gs','utf8'),ctx);
  return {ctx,props,source,sheets,ss,charts,get released(){return released}};
}
const head=['День','Устройств','Из них как приложение'];
test('migration preserves legacy history, backs it up once, and categories reconcile',()=>{
  const f=fixture([head,['2026-11-18',20,8],['2026-11-19',4,1]]);
  const before=structuredClone(f.source.data);
  f.ctx.doGet({parameter:{v:'2',app:'1',dev:'k',os:'w',br:'f'}});
  assert.deepEqual(f.source.data[1],before[1]);
  assert.deepEqual(Array.from(f.sheets[1].data),before);
  assert.equal(f.source.data[2][1],5);assert.equal(f.source.data[2][2],2);
  assert.equal(f.source.data[2][4],1);assert.equal(f.source.data[2][6],1);
  assert.equal(f.source.data[2].slice(7,14).reduce((a,b)=>a+b,0),1);
  assert.equal(f.source.data[2].slice(14).reduce((a,b)=>a+b,0),1);
  assert.equal(f.source.data[2][9],1);assert.equal(f.source.data[2][18],1);
  f.ctx.doGet({parameter:{app:'0',dev:'t'}});
  assert.equal(f.source.data[2][1],6);assert.equal(f.source.data[2][6],1);
  assert.equal(f.sheets.length,2);assert.equal(f.released,2);
});
test('unknown categories go to explicit buckets; no untrusted text is stored',()=>{
  const f=fixture([head]);f.ctx.doGet({parameter:{v:'2',dev:'=IMPORTXML(...)',os:'=bad',br:'user@example.com'}});
  const r=f.source.data[1];assert.equal(r[13],1);assert.equal(r[21],1);
  assert.equal(r.slice(3,6).reduce((a,b)=>a+b,0),0);
  assert.ok(r.slice(1).every(v=>typeof v==='number'));
});
test('reports are repeatable, own their sheet, and do not replace source or backup',()=>{
  const f=fixture([head,['2026-11-18',20,8]]);
  f.ctx.podgotovitOtchet();
  const report=f.ss.getSheetByName('Статистика устройств');
  const source=structuredClone(f.source.data), backup=structuredClone(f.sheets[1].data);
  assert.equal(report.charts.length,3);
  assert.match(report.data[5][1],/SUMIFS/);assert.match(report.data[8][1],/^=SUM\(/);
  assert.match(report.data[5][4],/'Счётчик'!G2:G/);
  f.ctx.podgotovitOtchet();assert.equal(f.sheets.length,3);assert.equal(report.charts.length,3);
  assert.deepEqual(f.source.data,source);assert.deepEqual(f.sheets[1].data,backup);
  f.sheets.unshift(f.sheets.pop());assert.equal(f.ctx.list_(),f.source);
});
test('unexpected headers, missing table, foreign report and timezone fail without destructive edits',()=>{
  let f=fixture([['unrelated','table','data']]);assert.throws(()=>f.ctx.doGet({}),/заголовок/);assert.equal(f.sheets.length,1);
  f=fixture([head]);delete f.props.table;assert.throws(()=>f.ctx.list_(),/table/);
  f=fixture([head]);f.ss.insertSheet('Статистика устройств');assert.throws(()=>f.ctx.podgotovitOtchet(),/уже существует/);assert.equal(f.sheets.length,2);
  f=fixture([head]);f.ss.tz='America/New_York';assert.throws(()=>f.ctx.podgotovitOtchet(),/пояс/);assert.equal(f.sheets.length,1);
});
