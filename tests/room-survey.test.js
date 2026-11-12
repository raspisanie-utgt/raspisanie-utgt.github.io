const assert = require('node:assert/strict');
const { test } = require('node:test');
const { questions, roomNumber } = require('../site/room-survey');
const period = { validFrom: '2026-09-01', validTo: '2027-01-11' };
const ask = (schedule, group = schedule.group, date = '2026-11-12') => questions(schedule, group, date, period);

test('a specific unknown Friday slot disappears when a verified room is supplied', () => {
  const group = { group: '21-С', verified: true, days: {
    5: [{ lessons: [3, 4], subject: 'Математические методы', room: '?' }],
    6: [{ lessons: [3, 4], subject: 'Математические методы', room: '1-3' }]
  } };
  const [q] = ask(group);
  assert.equal(ask(group).length, 1);
  assert.deepEqual([q.day, q.lessons], [5, [3, 4]]);
  group.days[5].find(row => row.subject === q.subject).room = '1-3';
  assert.deepEqual(ask(group), []);
  group.days[5][0].room = '?';
  assert.deepEqual(ask(group, '11-А'), []);
  assert.deepEqual(ask(group, group.group, '2027-01-12'), []);
});

test('questions are bounded and skip activities or overlapping rows with ambiguous rooms', () => {
  const group = { group: '11-А', verified: true, days: { 1: [
    { lessons: [0], subject: 'Разговоры о важном', room: '' },
    { lessons: [1], subject: 'Производственная практика', room: '' },
    { lessons: [2], subject: 'Физика', room: '?' },
    { lessons: [2], subject: 'Физика', room: '1-25' },
    ...[3, 4, 5, 6].map(n => ({ lessons: [n], subject: 'Математика', room: '2-?' }))
  ] } };
  assert.deepEqual(ask(group).map(q => [q.lessons[0], q.building]), [[3, '2'], [4, '2'], [5, '2']]);
  assert.deepEqual(ask({ ...group, verified: false }), []);
});

test('blank answers are allowed and only a classroom number in the requested building validates', () => {
  assert.deepEqual(roomNumber(''), { valid: true, value: '' });
  assert.deepEqual(roomNumber(' 2 — 1е ', '2'), { valid: true, value: '2-1Е' });
  for (const input of ['name@example.com', '2-15 Иван', '1-8', '2-00', '2-12-4']) {
    assert.equal(roomNumber(input, '2').valid, false, input);
  }
});
