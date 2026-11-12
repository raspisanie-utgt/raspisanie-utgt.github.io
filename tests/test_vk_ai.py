import datetime as dt
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from requests import Timeout

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import vk_ai
import vk_zamena

DATE = "2026-11-06"
ROW = {"group": "11-А", "lessons": [3, 4], "time": "", "subject": "Физика", "room": "1-81"}
NEXT = {**ROW, "lessons": [5, 6], "subject": "Математика"}
ENV = {"OPENROUTER_MODE": "suggest", "OPENROUTER_API_KEY": "test", "OPENROUTER_MODELS": "a,b"}
ROOMS = {"1-81", "1-3"}


def reading(model="a", pages=None, complete=True, date=DATE):
    return vk_ai.Reading(model, json.dumps({"date": date, "pages": pages or [[ROW, NEXT]]},
                                           ensure_ascii=False), complete)


class VisionTests(unittest.TestCase):
    def verify(self, response, counts=(2,)):
        return vk_ai._checked_rows(response, DATE, counts, {"11-А"},
                                   {"11-А": {3, 4, 5}}, {"11:00": 3}, ROOMS)

    def suggest(self, first, second):
        with patch.dict(os.environ, ENV, clear=True), patch.object(vk_ai, "_recognize", side_effect=[first, second]):
            return vk_ai.suggest([], DATE, [2], {"11-А"}, {}, {}, ROOMS)

    def test_preserves_room_and_positions(self):
        answer = reading()
        rows, problems = self.verify(vk_ai.Reading(answer.model, "```json\n" + answer.text + "\n```", True))
        self.assertEqual(problems, [])
        self.assertEqual([row[:2] for row in rows], [(1, 1), (1, 2)])
        self.assertEqual(rows[0][2][-1], "1-81")

    def test_checks_all_pages_and_every_row(self):
        response = reading(pages=[[ROW], [{**NEXT, "group": "?"}, {**NEXT, "room": None}]])
        _, problems = self.verify(response, (1, 2))
        self.assertEqual(len(problems), 2)
        self.assertIn("лист 2, строка 2", problems[1])
        self.assertTrue(self.verify(reading(pages=[[ROW]]))[1])
        self.assertTrue(self.verify(reading(), (None,))[1])
        self.assertTrue(self.verify(reading(date="2026-11-07"))[1])

    def test_requires_every_cancelled_lesson_and_detects_conflict_with_time(self):
        cancel = {**NEXT, "subject": "Отменить", "room": ""}
        timed = {**ROW, "lessons": [], "time": "11:00", "subject": "Химия"}
        _, problems = self.verify(reading(pages=[[ROW, timed, cancel]]), (3,))
        self.assertIn("конфликт", problems[0])
        self.assertIn("отменяемые уроки", problems[1])
        _, problems = self.verify(reading(pages=[[ROW, ROW]]))
        self.assertTrue(all("повтор" in p for p in problems))
        _, problems = self.verify(reading(pages=[[ROW, {**NEXT, "room": "1-31|"}]]))
        self.assertIn("кабинет не подтверждён", problems[0])

    def test_requires_two_actual_models_and_same_positions(self):
        first = reading("one:free")
        for second in (reading("one"), reading("two", [[NEXT, ROW]]),
                       reading("two", complete=False), reading("openrouter/free"), Timeout("secret from transport")):
            summary, _ = self.suggest(first, second)
            self.assertIn("не подтверждено", summary)
        _, report = self.suggest(first, Timeout("secret from transport"))
        self.assertIn("Timeout", report)
        self.assertNotIn("secret from transport", report)
        second = reading("two")
        summary, report = self.suggest(first, second)
        self.assertIn("совпали по всем строкам (2)", summary)
        self.assertEqual(report.count(first.text), 2)

    def test_publish_mode_and_missing_key_do_not_call_openrouter(self):
        with patch.dict(os.environ, {"OPENROUTER_MODE": "publish"}, clear=True), patch.object(vk_ai, "_recognize") as request:
            self.assertIsNone(vk_ai.suggest([], DATE, [2], {"11-А"}, {}, {}, ROOMS))
            os.environ["OPENROUTER_MODE"] = "suggest"
            self.assertIn("ключ", vk_ai.suggest([], DATE, [2], {"11-А"}, {}, {}, ROOMS)[0])
            request.assert_not_called()

    def test_reads_actual_model_and_end_reason_from_api_response(self):
        with patch("requests.post") as post:
            post.return_value.json.return_value = {
                "model": "actual",
                "choices": [{"finish_reason": "length", "message": {"content": "partial"}}],
            }
            answer = vk_ai._recognize("configured", [{"type": "text", "text": "test"}], "test-key")
        self.assertEqual(answer, vk_ai.Reading("actual", "partial", False))
        self.assertEqual(post.call_args.kwargs["json"]["model"], "configured")

    def test_date_fallback_requires_independent_agreement_in_range(self):
        today = dt.date.fromisoformat(DATE)
        def result(first, second):
            with (patch.dict(os.environ, ENV, clear=True),
                  patch.object(vk_ai, "_recognize", side_effect=[first, second])):
                return vk_ai.suggest_date([], today)
        first = vk_ai.Reading("one:free", DATE, True)
        self.assertEqual(result(first, vk_ai.Reading("two", DATE, True))[0], DATE)
        for other in (vk_ai.Reading("one", DATE, True), vk_ai.Reading("two", "2026-11-07", True),
                      vk_ai.Reading("two", "2025-11-06", True), Timeout("internal")):
            self.assertIsNone(result(first, other)[0])
        self.assertIn("Timeout", result(first, Timeout("internal"))[1])


class WorkflowTests(unittest.TestCase):
    def test_suggestion_cannot_publish_even_if_confirmed(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo, output = Path(tmp) / "photo.png", Path(tmp) / "zameny"
            photo.write_bytes(b"fake photo")
            table = {"ok": True, "group_doubt": True, "rows": [], "title": ""}
            with (patch.dict(os.environ, ENV, clear=True),
                  patch.object(vk_zamena, "date_from_image", return_value=(DATE, "текст OCR")),
                  patch.object(vk_zamena, "suggestion_context", return_value=({}, {})),
                  patch.object(vk_zamena.vk_ai, "suggest", return_value=("совпали 2 строки", "Физика\n" * 1000)),
                  patch.multiple(vk_zamena.scraper, subject_vocab=lambda: [], ocr_table=lambda *a, **k: table,
                                 check_with_schedule=lambda *a: None, week_doubt=lambda *a: False,
                                 apply_manual=lambda *a: None, known_groups=lambda: ["11-А"], known_rooms=lambda: ROOMS)):
                res = vk_zamena.publish([photo], out_dir=output, today=dt.date.fromisoformat(DATE))
            self.assertEqual(res["status"], "uncertain")
            self.assertFalse(output.exists())
            self.assertIn("Физика\n" * 1000, res["reason"])
            self.assertLessEqual(len(res["text"]), vk_zamena.TEXT_LIMIT)

    def test_writes_all_messages_and_preserves_legacy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            incoming = root / "vk-incoming"
            incoming.mkdir()
            for name in ("10_1.png", "20_1.png", "20_2.png"):
                (incoming / name).touch()
            full = "OCR сомневается" + vk_zamena.AI_REPORT_MARKER + "Физика\n" * 1000
            with patch.object(vk_zamena, "publish", side_effect=lambda *a, **k: {
                "status": "uncertain", "reason": full,
            }) as publish:
                vk_zamena.process_incoming(root, log=lambda _: None)
                self.assertEqual(len(publish.call_args.args[0]), 2)
            self.assertEqual(list(incoming.iterdir()), [])
            batch = json.loads((root / "vk-results.json").read_text(encoding="utf-8"))["results"]
            legacy = json.loads((root / "vk-result.json").read_text(encoding="utf-8"))
            self.assertEqual([res["msg"] for res in batch], ["10", "20"])
            self.assertEqual(batch[1]["reason"], full)
            self.assertEqual(legacy["msg"], "20")
            self.assertIn("Физика", legacy["reason"])
            self.assertEqual(len(list((root / "vk-review").glob("*/*.png"))), 3)
            vk_zamena.write_result({"status": "already", "msg": "10"}, root)
            batch = json.loads((root / "vk-results.json").read_text(encoding="utf-8"))["results"]
            self.assertEqual([res["msg"] for res in batch], ["10", "20", "10"])

    def test_keeps_photos_if_report_write_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            incoming = root / "vk-incoming"
            incoming.mkdir()
            photo = incoming / "10_1.png"
            photo.touch()
            with (patch.object(vk_zamena, "publish", return_value={"status": "uncertain"}),
                  patch.object(vk_zamena, "write_results", side_effect=OSError)):
                with self.assertRaises(OSError):
                    vk_zamena.process_incoming(root, log=lambda _: None)
            self.assertTrue(photo.exists())

    def test_issue_body_keeps_normal_report_and_links_long_report(self):
        body = vk_zamena.issue_body(DATE, ["11-А"], "Первая строка\nПоследняя строка", "кратко", "20")
        self.assertIn("Первая строка\n    Последняя строка", body)
        long = vk_zamena.issue_body(DATE, [], "Ф" * 40000, "кратко", "20")
        self.assertLess(len(long.encode("utf-8")), vk_zamena.ISSUE_BODY_BYTES)
        self.assertIn("сообщения 20", long)
        self.assertIn("data/vk-results.json", long)

    def test_large_table_reaches_legacy_issue_and_full_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            groups = {"11-А", "11-П", "11-В"}
            page = [{**ROW, "group": group, "lessons": [i],
                     "subject": f"Дисциплина {group} {i}. " + "Длинное название дисциплины " * 4}
                    for group in sorted(groups) for i in range(1, 11)]
            first, second = reading("a", [page]), reading("b", [page])
            with (patch.dict(os.environ, ENV, clear=True),
                  patch.object(vk_ai, "_recognize", side_effect=[first, second])):
                summary, report = vk_ai.suggest([], DATE, [30], groups, {}, {}, ROOMS)
            self.assertIn("по всем строкам (30)", summary)
            self.assertEqual(report.count(first.text), 2)
            reason = "OCR сомневается" + vk_zamena.AI_REPORT_MARKER + report
            vk_zamena.write_result({"msg": "30", "status": "uncertain", "reason": reason, "text": "кратко"}, root)
            legacy = json.loads((root / "vk-result.json").read_text(encoding="utf-8"))
            self.assertIn(page[-1]["subject"], legacy["reason"])
            self.assertEqual(vk_zamena.read_results(root)[0]["reason"], reason)
            vk_zamena.write_result({"msg": "30", "status": "uncertain", "reason": reason * 8, "text": "кратко"}, root)
            legacy = json.loads((root / "vk-result.json").read_text(encoding="utf-8"))
            self.assertIn("vk-results.json", legacy["reason"])
            self.assertEqual(vk_zamena.read_results(root)[-1]["reason"], reason * 8)

    def test_replayed_message_reuses_report_and_retries_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            incoming = root / "vk-incoming"
            incoming.mkdir()
            photo = incoming / "10_1.png"
            photo.write_bytes(b"original")
            (incoming / "10_2.png").write_bytes(b"second page")
            result = {"status": "uncertain", "reason": "неуверенно"}
            with patch.object(vk_zamena, "publish", return_value=result) as publish:
                vk_zamena.process_incoming(root, log=lambda _: None)
                saved = (root / "vk-result.json").read_bytes()
                photo.write_bytes(b"original")
                self.assertEqual(vk_zamena.process_incoming(root, log=lambda _: None), [])
                publish.assert_called_once()
            self.assertFalse(photo.exists())
            self.assertEqual((root / "vk-result.json").read_bytes(), saved)
            self.assertEqual({p.read_bytes() for p in (root / "vk-review").glob("*/*.png")},
                             {b"original", b"second page"})

    def test_repeated_failure_keeps_source_and_legacy_notification_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            incoming = root / "vk-incoming"
            incoming.mkdir()
            photo = incoming / "10_1.png"
            photo.write_bytes(b"original")
            with patch.object(vk_zamena, "publish", side_effect=OSError):
                self.assertEqual(vk_zamena.process_incoming(root, log=lambda _: None)[0]["status"], "error")
                saved = (root / "vk-result.json").read_bytes()
                self.assertEqual(vk_zamena.process_incoming(root, log=lambda _: None), [])
            self.assertEqual(photo.read_bytes(), b"original")
            self.assertEqual((root / "vk-result.json").read_bytes(), saved)

    def test_existing_manual_day_bypasses_ocr_and_openrouter(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            original = folder / f"{DATE}.json"
            photo = folder / "new.png"
            photo.write_bytes(b"published photo")
            existing = json.dumps({"manual": "checked", "all_changes": {},
                                   "images": [{"sha1": hashlib.sha1(photo.read_bytes()).hexdigest()}]}).encode()
            original.write_bytes(existing)
            with (patch.dict(os.environ, ENV, clear=True),
                  patch.object(vk_zamena, "date_from_image", return_value=(DATE, "")),
                  patch.object(vk_zamena.scraper, "ocr_table") as ocr,
                  patch.object(vk_ai, "_recognize") as request):
                self.assertEqual(vk_zamena.publish([photo], out_dir=folder)["status"], "already")
                incoming = folder / vk_zamena.INCOMING
                incoming.mkdir()
                extra = incoming / "90_1.png"
                extra.write_bytes(b"additional photo")
                results = vk_zamena.process_incoming(folder, out_dir=folder)
                self.assertEqual(results[0]["status"], "uncertain")
                self.assertIn("дополнение", results[0]["reason"])
                self.assertEqual(vk_zamena.process_incoming(folder, out_dir=folder), [])
                archive = vk_zamena.review_folder(folder, results[0]["inputs"])
                self.assertEqual((archive / extra.name).read_bytes(), b"additional photo")
                self.assertFalse(vk_zamena.scraper.process_block({"date": DATE}, None, [], out_dir=folder))
                ocr.assert_not_called()
                request.assert_not_called()
            self.assertEqual(original.read_bytes(), existing)

    def test_oversize_order_is_not_truncated(self):
        files = [Path(f"{i}.png") for i in range(vk_zamena.MAX_PHOTOS + 1)]
        with patch.object(vk_zamena, "date_from_image") as read:
            result = vk_zamena.publish(files)
        self.assertEqual(result["status"], "uncertain")
        self.assertIn("полный комплект", result["reason"])
        read.assert_not_called()

    def test_missing_ocr_date_never_creates_schedule(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with (patch.object(vk_zamena, "date_from_image", return_value=(None, "шапка")),
                  patch.object(vk_ai, "suggest_date", return_value=(DATE, "две модели")),
                  patch.object(vk_zamena.scraper, "ocr_table") as ocr):
                result = vk_zamena.publish([folder / "photo.jpg"], out_dir=folder / "out")
            self.assertEqual((result["status"], result["suggested_date"]), ("no_date", DATE))
            self.assertIn("Нужна ручная проверка", result["reason"])
            self.assertFalse((folder / "out").exists())
            ocr.assert_not_called()

    def test_confident_wrong_room_gets_checked_without_an_api_call_on_agreement(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            photo = folder / "photo.jpg"
            photo.write_bytes(b"photo")
            row = {**ROW, "uncertain": False}
            first = {"ok": True, "title": "", "rows": [row]}
            second = {**first, "rows": [{**row, "room": "1-8"}]}
            with (patch.object(vk_zamena, "date_from_image", return_value=(DATE, "")),
                  patch.multiple(vk_zamena.scraper, subject_vocab=lambda: [],
                                 check_with_schedule=lambda *a: None, week_doubt=lambda *a: False,
                                 apply_manual=lambda *a: None),
                  patch.object(vk_zamena, "add_ai_suggestion") as suggest):
                for reread, status in ((second, "uncertain"), (first, "ok")):
                    with patch.object(vk_zamena.scraper, "ocr_table", side_effect=[first, reread]) as ocr:
                        result = vk_zamena.publish([photo], out_dir=folder / "out", dry=True)
                    self.assertEqual(result["status"], status)
                    self.assertTrue(ocr.call_args.kwargs["alternate"])
                suggest.assert_called_once()
            self.assertFalse((folder / "out").exists())

    def test_history_survives_overflow_and_recovers_corrupt_main(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pending = root / vk_zamena.INCOMING
            pending.mkdir()
            history = [{"msg": str(i), "status": "uncertain"} for i in range(125)]
            vk_zamena.write_results(history, root)
            vk_zamena.write_result({"msg": "new", "status": "ok"}, root)
            queue = root / vk_zamena.RESULT_QUEUE
            queue.write_text('{"results":[null]}', encoding="utf-8")
            self.assertEqual(vk_zamena.process_incoming(root), [])
            self.assertEqual(len(vk_zamena.read_results(root)), 126)
            self.assertEqual(queue.read_bytes(), (root / vk_zamena.RESULT_BACKUP).read_bytes())
            queue.write_bytes(b"{")
            (root / vk_zamena.RESULT_BACKUP).write_bytes(b"{")
            photo = pending / "9_1.jpg"
            photo.write_bytes(b"original")
            with self.assertRaises(ValueError):
                vk_zamena.process_incoming(root)
            self.assertEqual(photo.read_bytes(), b"original")

    def test_late_page_reuses_preserved_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pending = root / vk_zamena.INCOMING
            pending.mkdir()
            first = pending / "90_1.jpg"
            first.write_bytes(b"original")
            with patch.object(vk_zamena, "publish", side_effect=lambda *a, **kw: {"status": "uncertain"}) as publish:
                vk_zamena.process_incoming(root, log=lambda _: None)
                self.assertFalse(first.exists())
                (pending / "90_2.jpg").write_bytes(b"continuation")
                vk_zamena.process_incoming(root, log=lambda _: None)
                self.assertEqual([p.name for p in publish.call_args.args[0]], ["90_1.jpg", "90_2.jpg"])
            self.assertEqual(len(vk_zamena.read_results(root)), 2)
