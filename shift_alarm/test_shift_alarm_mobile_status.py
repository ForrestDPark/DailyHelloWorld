import datetime
import json
import os
import tempfile
import unittest

from shift_alarm import (
    _context_key_for_date, _parse_reminder_time_row, build_daily_routine, build_reminder_schedule,
    build_sleep_schedule,
    build_reminders_detailed, filter_dismissed_reminder_items, _effective_reminder_definitions,
    _generic_recurrence_due, _post_shift_volume_time, POST_SHIFT_VOLUME_DELAY_HOURS,
)


class PostShiftVolumeTimeTests(unittest.TestCase):
    # ★ 2026-09-24: "근무표기준으로 퇴근후 한시간뒤에는 맥음량 50%로
    # 낮춰주면좋겠어" 요청 — 근무별 퇴근 시각 + 지연 시간 계산만 따로
    # 검증한다(rumps 타이머 콜백 자체는 App 인스턴스가 필요해 여기서 안 다룸).
    def test_day_shift_ends_at_2pm_so_target_is_3pm(self):
        self.assertEqual(_post_shift_volume_time("Day"), (14 + POST_SHIFT_VOLUME_DELAY_HOURS, 0))

    def test_swing_shift_ends_at_10pm_so_target_is_11pm(self):
        self.assertEqual(_post_shift_volume_time("Swing"), (22 + POST_SHIFT_VOLUME_DELAY_HOURS, 0))

    def test_gy_shift_ends_at_6am_so_target_is_7am(self):
        self.assertEqual(_post_shift_volume_time("GY"), (6 + POST_SHIFT_VOLUME_DELAY_HOURS, 0))

    def test_returns_none_for_unknown_or_day_off_shift(self):
        self.assertIsNone(_post_shift_volume_time("휴무"))
        self.assertIsNone(_post_shift_volume_time(None))


class RemindersDetailedTests(unittest.TestCase):
    def test_exports_label_time_and_checked(self):
        items = [("laundry", "🧺 빨래 돌리는 날")]
        definitions = {
            "laundry": {"time": {"hour": 11, "minute": 30}},
        }
        self.assertEqual(
            build_reminders_detailed(items, definitions, {"🧺 빨래 돌리는 날": True}),
            [{"label": "🧺 빨래 돌리는 날", "time": "11:30", "checked": True}],
        )

    def test_preserves_order_and_defaults_unchecked(self):
        items = [("a", "첫째"), ("b", "둘째")]
        definitions = {
            "a": {"time": {"hour": 9, "minute": 5}},
            "b": {"time": {"hour": 20, "minute": 0}},
        }
        self.assertEqual(
            build_reminders_detailed(items, definitions),
            [
                {"label": "첫째", "time": "09:05", "checked": False},
                {"label": "둘째", "time": "20:00", "checked": False},
            ],
        )

    def test_missing_or_invalid_time_is_null(self):
        items = [("missing", "미설정"), ("invalid", "오류")]
        definitions = {"invalid": {"time": {"hour": "9", "minute": 0}}}
        self.assertEqual(
            build_reminders_detailed(items, definitions),
            [
                {"label": "미설정", "time": None, "checked": False},
                {"label": "오류", "time": None, "checked": False},
            ],
        )

    def test_uses_resolved_context_time_when_provided(self):
        items = [("laundry", "빨래")]
        definitions = {"laundry": {"time": {"hour": 11, "minute": 30}}}
        resolved = {"laundry": {"hour": 18, "minute": 0}}
        self.assertEqual(
            build_reminders_detailed(items, definitions, resolved_times=resolved)[0]["time"],
            "18:00",
        )


class ReminderScheduleTests(unittest.TestCase):
    def test_generic_day_week_and_month_recurrence(self):
        day = datetime.date(2026, 9, 20)
        self.assertTrue(_generic_recurrence_due(
            {"unit": "days", "interval": 3, "anchor": "2026-09-17"}, day
        ))
        self.assertTrue(_generic_recurrence_due(
            {"unit": "weeks", "interval": 1, "anchor": "2026-09-13"}, day
        ))
        self.assertTrue(_generic_recurrence_due(
            {"unit": "months", "interval": 2, "anchor": "2026-07-20"}, day
        ))

    def test_editor_can_add_override_and_delete_definitions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "reminders.json")
            with open(path, "w", encoding="utf-8") as file:
                json.dump({"items": {
                    "laundry": {"label": "빨래 수정", "enabled": False},
                    "call_mom": {"deleted": True},
                    "custom_test": {"label": "테스트", "enabled": True, "custom": True,
                                    "time": {"hour": 8, "minute": 5}},
                }}, file, ensure_ascii=False)
            definitions = _effective_reminder_definitions(path)
        self.assertEqual(definitions["laundry"]["label"], "빨래 수정")
        self.assertFalse(definitions["laundry"]["enabled"])
        self.assertNotIn("call_mom", definitions)
        self.assertEqual(definitions["custom_test"]["time"], {"hour": 8, "minute": 5})

    def test_exports_current_full_schedule_without_secrets(self):
        definitions = {
            "laundry": {
                "label": "🧺 빨래", "time": {"hour": 11, "minute": 30},
                "enabled": True,
            },
            "optional": {"label": "선택", "time": None, "enabled": False},
        }
        rows = build_reminder_schedule(definitions, {
            "laundry": {"Swing": {"hour": 9, "minute": 0}},
        })
        self.assertEqual(rows[0]["time"], "11:30")
        self.assertEqual(rows[0]["times"]["시각"], "11:30")
        self.assertEqual(rows[0]["times"]["Swing"], "09:00")
        self.assertIsNone(rows[0]["times"]["Day"])
        self.assertEqual(rows[1]["time"], None)
        self.assertEqual(rows[1]["times"]["시각"], None)

    def test_daily_routine_preserves_order_and_booleanizes(self):
        self.assertEqual(build_daily_routine({"물 마시기": 1, "독서": False}), [
            {"label": "물 마시기", "checked": True},
            {"label": "독서", "checked": False},
        ])

    def test_sleep_schedule_contains_shift_wake_and_transition_melatonin_times(self):
        rows = {item["key"]: item for item in build_sleep_schedule()}
        self.assertEqual(rows["wake_shift"]["times"]["Day"], "02:55")
        self.assertEqual(rows["wake_shift"]["times"]["Swing"], "08:30")
        self.assertEqual(rows["wake_shift"]["times"]["GY"], "16:30")
        self.assertEqual(rows["melatonin_swing_day"]["times"]["S-D휴"], "20:00")
        self.assertTrue(rows["melatonin_swing_day"]["editable"])
        self.assertTrue(rows["wake_shift"]["auto_schedule"])
        self.assertEqual(rows["wake_gy_swing_day2"]["default_recurrence_text"],
                         "G→S 전환 휴무 둘째날마다")


class ReminderContextTests(unittest.TestCase):
    def test_parses_actual_eight_column_table_order(self):
        label, base, times = _parse_reminder_time_row([
            "빨래", "11:30", "12:00", "15:00", "18:00", "06:30", "09:00", "20:00",
        ])
        self.assertEqual(label, "빨래")
        self.assertEqual(base, {"hour": 11, "minute": 30})
        self.assertEqual(times["Swing"], {"hour": 12, "minute": 0})
        self.assertEqual(times["G-S휴"], {"hour": 20, "minute": 0})

    def test_blank_context_cells_are_omitted_for_base_fallback(self):
        _label, base, times = _parse_reminder_time_row(
            ["독서", "21:00", "", "", "", "", "", ""]
        )
        self.assertEqual(base, {"hour": 21, "minute": 0})
        self.assertEqual(times, {})

    def test_work_shift_profiles(self):
        d = datetime.date(2026, 1, 10)
        for code, expected in (("S", "Swing"), ("D", "Day"), ("G", "GY")):
            self.assertEqual(_context_key_for_date({d.isoformat(): code}, d), expected)

    def test_transition_off_profiles_reuse_schedule_helpers(self):
        d = datetime.date(2026, 1, 10)
        cases = [
            ("S", "D", "S-D휴"),
            ("D", "G", "D-G휴"),
            ("G", "S", "G-S휴"),
        ]
        for before, after, expected in cases:
            schedule = {
                (d - datetime.timedelta(days=1)).isoformat(): before,
                d.isoformat(): "휴",
                (d + datetime.timedelta(days=1)).isoformat(): after,
            }
            self.assertEqual(_context_key_for_date(schedule, d), expected)


class ReminderDismissalTests(unittest.TestCase):
    def test_filters_only_exact_labels_for_requested_day(self):
        day = datetime.date(2026, 9, 7)
        items = [("laundry", "빨래"), ("reading", "독서")]
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "dismissed.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({day.isoformat(): ["빨래"], "2026-09-08": ["독서"]}, f)
            self.assertEqual(
                filter_dismissed_reminder_items(items, day, path),
                [("reading", "독서")],
            )

    def test_missing_or_malformed_file_is_fail_open(self):
        day = datetime.date(2026, 9, 7)
        items = [("laundry", "빨래")]
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = os.path.join(temp_dir, "missing.json")
            self.assertEqual(filter_dismissed_reminder_items(items, day, missing), items)
            malformed = os.path.join(temp_dir, "malformed.json")
            with open(malformed, "w", encoding="utf-8") as f:
                f.write("{")
            self.assertEqual(filter_dismissed_reminder_items(items, day, malformed), items)

    def test_next_day_recurrence_is_not_deleted(self):
        deleted_day = datetime.date(2026, 9, 7)
        next_day = deleted_day + datetime.timedelta(days=1)
        items = [("laundry", "빨래")]
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "dismissed.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({deleted_day.isoformat(): ["빨래"]}, f)
            self.assertEqual(filter_dismissed_reminder_items(items, deleted_day, path), [])
            self.assertEqual(filter_dismissed_reminder_items(items, next_day, path), items)

if __name__ == "__main__":
    unittest.main()
