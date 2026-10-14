import unittest
import datetime as dt
from kbo_alarm import parse_games, EASTERN

class ScheduleTests(unittest.TestCase):
    def test_doosan_only_rowspan_cancellation_and_timezone(self):
        html = '''<table><tbody>
        <tr><td class="day" rowspan="4">10.14(수)</td><td>18:30</td><td class="play">두산 VS LG</td></tr>
        <tr><td>18:30</td><td class="play">삼성 VS 롯데</td></tr>
        <tr><td>18:30</td><td class="play">두산 VS KT</td><td>우천취소</td></tr>
        <tr><td>18:30</td><td class="play">두산 VS LG</td></tr>
        </tbody></table>'''
        games = parse_games(html, 2026, 10)
        self.assertEqual(len(games), 1)
        self.assertEqual(games[0]['start'], '2026-10-14T05:30:00-04:00')

    def test_no_inference_from_team_filter(self):
        self.assertEqual(parse_games('<select><option>두산</option></select>',2026,10), [])

    def test_winter_eastern_offset(self):
        html = '<table><tbody><tr><td class="day">11.10</td><td>18:30</td><td class="play">Doosan VS LG</td></tr></tbody></table>'
        self.assertEqual(parse_games(html,2026,11)[0]['start'], '2026-11-10T04:30:00-05:00')

if __name__ == '__main__':
    unittest.main()

class WindowsTaskTests(unittest.TestCase):
    def test_interactive_wake_task_and_eastern_conversion(self):
        from unittest.mock import patch
        from pathlib import Path
        import tempfile
        import kbo_alarm
        scripts = []
        def capture(command, check):
            scripts.append(Path(command[-1]).read_text(encoding='utf-8-sig'))
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(kbo_alarm, 'windows_only'), patch.object(kbo_alarm, 'DATA', Path(tmp)), patch.object(kbo_alarm.subprocess, 'run', side_effect=capture):
                kbo_alarm.schedule(dt.datetime(2099, 10, 14, 5, 30, tzinfo=EASTERN), 60)
        self.assertIn('-WakeToRun', scripts[0])
        self.assertIn('-LogonType Interactive', scripts[0])
        self.assertIn('play --volume 60', scripts[0])
        self.assertIn('-ExecutionTimeLimit ([timespan]::Zero)', scripts[0])
        self.assertNotIn('-AllowStartIfOnBatteries', scripts[0])

    def test_past_alarm_rejected(self):
        from unittest.mock import patch
        import kbo_alarm
        with patch.object(kbo_alarm, 'windows_only'):
            with self.assertRaises(ValueError):
                kbo_alarm.schedule(dt.datetime(2000, 1, 1, tzinfo=EASTERN), 60)
