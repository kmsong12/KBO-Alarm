"""Local Windows wake-and-watch CLI. All user times are America/New_York."""
import argparse
import ctypes
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup

EASTERN = ZoneInfo('America/New_York')
KOREA = ZoneInfo('Asia/Seoul')
ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'KBO-Alarm'
SCHEDULE = 'https://www.koreabaseball.com/Schedule/Schedule.aspx'


def parse_games(html, year, month):
    """Parse official schedule rows, including dates carried by rowspan."""
    soup = BeautifulSoup(html, 'html.parser')
    games, day = [], None
    for row in soup.select('table tbody tr'):
        cells = row.find_all('td', recursive=False)
        date_cell = row.select_one('td.day')
        if date_cell:
            match = re.search(r'(\d{1,2})\.(\d{1,2})', date_cell.get_text(' ', strip=True))
            if match:
                day = dt.date(year, int(match[1]), int(match[2]))
        if day is None:
            continue
        # The matchup cell contains team names; do not match page-wide team filters.
        matchup = row.select_one('td.play')
        if matchup is None:
            continue
        title = matchup.get_text(' ', strip=True)
        if not re.search(r'두산|\bDoosan\b', title, re.I):
            continue
        text = row.get_text(' ', strip=True)
        if re.search(r'취소|우천|cancel', text, re.I):
            continue
        clock = next((re.fullmatch(r'(\d{1,2}):(\d{2})', c.get_text(strip=True)) for c in cells
                      if re.fullmatch(r'\d{1,2}:\d{2}', c.get_text(strip=True))), None)
        if not clock:
            continue
        kickoff = dt.datetime.combine(day, dt.time(int(clock[1]), int(clock[2])), KOREA)
        item = {'title': title, 'start': kickoff.astimezone(EASTERN).isoformat()}
        if item not in games:
            games.append(item)
    return games


def browser(p, headless=False):
    DATA.mkdir(parents=True, exist_ok=True)
    return p.chromium.launch_persistent_context(str(DATA / 'browser'), channel='msedge',
        headless=headless, args=['--autoplay-policy=no-user-gesture-required'])


def discover(days):
    from playwright.sync_api import sync_playwright
    now = dt.datetime.now(EASTERN)
    end = now + dt.timedelta(days=days)
    months = {(x.year, x.month) for x in [now.astimezone(KOREA), end.astimezone(KOREA)]}
    found = []
    with sync_playwright() as p:
        context = browser(p)
        page = context.pages[0] if context.pages else context.new_page()
        try:
            for year, month in sorted(months):
                # Official site uses ASP.NET dropdown postbacks. Inspect actual option values.
                page.goto(SCHEDULE, wait_until='networkidle')
                selectors = page.locator('select[id$="ddlSeries"]')
                series_values = selectors.locator('option').evaluate_all('(xs) => xs.map(x => x.value)') if selectors.count() else [None]
                for series in series_values:
                    page.goto(SCHEDULE, wait_until='networkidle')
                    page.locator('select[id$="ddlYear"]').select_option(str(year))
                    page.wait_for_load_state('networkidle')
                    page.locator('select[id$="ddlMonth"]').select_option(f'{month:02}')
                    page.wait_for_load_state('networkidle')
                    selector = page.locator('select[id$="ddlSeries"]')
                    if selector.count():
                        values = selector.locator('option').evaluate_all('(xs) => xs.map(x => x.value)')
                        if series not in values:
                            continue
                        selector.select_option(series)
                        page.wait_for_load_state('networkidle')
                    found.extend(parse_games(page.content(), year, month))
        finally:
            context.close()
    return sorted({(g['start'], g['title']) for g in found
                   if now <= dt.datetime.fromisoformat(g['start']) <= end})


def windows_only():
    if sys.platform != 'win32':
        raise RuntimeError('Scheduling and playback must run locally on your Windows laptop.')


def schedule(when, volume, task='KBO-Alarm'):
    windows_only()
    if when <= dt.datetime.now(EASTERN):
        raise ValueError('Choose a future Eastern date and time.')
    DATA.mkdir(parents=True, exist_ok=True)
    # Scheduler uses Windows local time. Convert Eastern rather than assuming machine timezone.
    local = when.astimezone().replace(tzinfo=None).isoformat(timespec='seconds')
    def psquote(value):
        return "'" + str(value).replace("'", "''") + "'"
    command = f'"{ROOT / "kbo_alarm.py"}" play --volume {volume}'
    script = f"""
$ErrorActionPreference = 'Stop'
$action = New-ScheduledTaskAction -Execute {psquote(sys.executable)} -Argument {psquote(command)} -WorkingDirectory {psquote(ROOT)}
$trigger = New-ScheduledTaskTrigger -Once -At ([datetime]{psquote(local)})
$settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable -ExecutionTimeLimit ([timespan]::Zero)
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName {psquote(task)} -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.ps1', delete=False, encoding='utf-8-sig') as f:
        f.write(script)
    try:
        subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', f.name], check=True)
    finally:
        Path(f.name).unlink(missing_ok=True)
    print(f'{task}: {when:%Y-%m-%d %I:%M %p %Z}. Keep plugged in, lid open, signed in and unlocked.')


def set_volume(percent):
    # Windows multimedia key: explicit unmute through Core Audio using PowerShell COM interop.
    source = r'''
using System;
using System.Runtime.InteropServices;
[ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] class Enumerator {}
[ComImport, Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IEnum { int NotUsed(); int GetDefaultAudioEndpoint(int flow,int role,out IDevice device); }
[ComImport, Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IDevice { int Activate(ref Guid iid,int context,IntPtr parameters,[MarshalAs(UnmanagedType.IUnknown)] out object result); }
[ComImport, Guid("5CDF2C82-841E-4546-9722-0CF74078229A"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IVolume {
 int Register(IntPtr p); int Unregister(IntPtr p); int Channels(out uint n);
 int SetLevel(float n,Guid g); int SetScalar(float n,Guid g); int GetLevel(out float n); int GetScalar(out float n);
 int SetChannel(uint c,float n,Guid g); int SetChannelScalar(uint c,float n,Guid g);
 int GetChannel(uint c,out float n); int GetChannelScalar(uint c,out float n);
 int SetMute([MarshalAs(UnmanagedType.Bool)] bool m,Guid g);
}
public class Audio {
 public static void Set(float level) {
  IDevice device; Marshal.ThrowExceptionForHR(((IEnum)new Enumerator()).GetDefaultAudioEndpoint(0,1,out device));
  Guid id = typeof(IVolume).GUID; object obj;
  Marshal.ThrowExceptionForHR(device.Activate(ref id,23,IntPtr.Zero,out obj));
  var volume=(IVolume)obj;
  Marshal.ThrowExceptionForHR(volume.SetMute(false,Guid.Empty));
  Marshal.ThrowExceptionForHR(volume.SetScalar(level,Guid.Empty));
 }
}
'''
    subprocess.run(['powershell.exe', '-NoProfile', '-Command',
                    "Add-Type -TypeDefinition @'\n" + source + "\n'@\n[Audio]::Set(" + str(percent / 100) + ')'], check=True)


def play(volume):
    windows_only()
    from playwright.sync_api import sync_playwright
    DATA.mkdir(parents=True, exist_ok=True)
    log = open(DATA / 'playback.log', 'a', encoding='utf-8', buffering=1)
    sys.stdout = sys.stderr = log
    set_volume(volume)
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000003)
    try:
        with sync_playwright() as p:
            context = browser(p)
            page = context.pages[0] if context.pages else context.new_page()
            deadline = time.monotonic() + 45 * 60
            while time.monotonic() < deadline:
                try:
                    page.goto('https://www.sooplive.com', wait_until='domcontentloaded')
                    search = page.locator('input[type="search"], input[placeholder*="Search"], input[placeholder*="검색"]')
                    if not search.count():
                        page.get_by_role('button', name=re.compile('search|검색', re.I)).first.click()
                    search.first.wait_for(state='visible', timeout=15000)
                    search.first.fill('doosan')
                    search.first.press('Enter')
                    page.wait_for_timeout(5000)
                    # Require both Doosan title and exact official channel in the same card.
                    cards = page.locator('a[href]').filter(has_text=re.compile('doosan|두산', re.I))
                    selected = None
                    for i in range(cards.count()):
                        card = cards.nth(i)
                        text = card.inner_text()
                        href = card.get_attribute('href') or ''
                        if not re.search(r'/live(?:/|\?|$)|play\.sooplive\.', href, re.I):
                            continue
                        if re.search(r'\bkbo_global[1-5]\b', text + ' ' + href, re.I):
                            selected = card
                            break
                    if selected is None:
                        raise RuntimeError('No Doosan live card from kbo_global1–5 found.')
                    prior_pages = list(context.pages)
                    selected.click()
                    page.wait_for_timeout(8000)
                    new_pages = [x for x in context.pages if x not in prior_pages]
                    if new_pages:
                        page = new_pages[-1]
                        page.wait_for_load_state('domcontentloaded')
                    for frame in page.frames:
                        buttons = frame.get_by_role('button', name=re.compile(r'^(play|재생)$', re.I))
                        if buttons.count():
                            buttons.first.click()
                        frame.locator('video').evaluate_all('(vs) => vs.forEach(v => {v.muted=false; v.volume=1; v.play().catch(()=>{});})')
                    time.sleep(3)
                    playing = any(frame.locator('video').evaluate_all(
                        '(vs) => vs.some(v => !v.paused && !v.muted && v.volume > 0 && v.currentTime > 0 && v.readyState >= 2)') for frame in page.frames)
                    if not playing:
                        raise RuntimeError('Could not verify playing, unmuted video; inspect the browser.')
                    print('Doosan stream is playing. Close the browser or press Ctrl+C to stop.', flush=True)
                    while context.pages:
                        page.wait_for_timeout(1000)
                    return
                except Exception as error:
                    print(f'{dt.datetime.now(EASTERN).isoformat()}: {error}', flush=True)
                    DATA.mkdir(parents=True, exist_ok=True)
                    if page.is_closed():
                        return
                    page.screenshot(path=str(DATA / 'last-failure.png'))
                    page.wait_for_timeout(30000)
            raise RuntimeError('No verified stream after 45 minutes. See last-failure.png.')
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    scan = commands.add_parser('games', help='Discover upcoming Doosan games and offer an alarm')
    scan.add_argument('--days', type=int, default=7, choices=range(1,29))
    scan.add_argument('--volume', type=int, default=60, choices=range(1,101))
    alarm = commands.add_parser('schedule', help='Schedule a known game in Eastern time')
    alarm.add_argument('--at', required=True, help='YYYY-MM-DD HH:MM (Eastern)')
    alarm.add_argument('--volume', type=int, default=60, choices=range(1,101))
    test = commands.add_parser('wake-test', help='Wake and attempt stream playback in a few minutes')
    test.add_argument('--minutes', type=int, default=3, choices=range(1,61))
    test.add_argument('--volume', type=int, default=60, choices=range(1,101))
    playback = commands.add_parser('play', help='Try Doosan playback immediately')
    playback.add_argument('--volume', type=int, default=60, choices=range(1,101))
    commands.add_parser('cancel', help='Remove the scheduled game task')
    args = parser.parse_args()
    try:
        if args.command == 'schedule':
            schedule(dt.datetime.strptime(args.at, '%Y-%m-%d %H:%M').replace(tzinfo=EASTERN), args.volume)
        elif args.command == 'wake-test':
            schedule(dt.datetime.now(EASTERN) + dt.timedelta(minutes=args.minutes), args.volume, 'KBO-Alarm-Test')
            print('Put Windows to Sleep now. If no Doosan stream is live, this tests wake/browser startup only.')
        elif args.command == 'play':
            play(args.volume)
        elif args.command == 'cancel':
            windows_only()
            subprocess.run(['schtasks.exe', '/Delete', '/TN', 'KBO-Alarm', '/F'], check=True)
        else:
            games = discover(args.days)
            if not games:
                print('No upcoming Doosan games found. Live site parsing has not been independently verified; check the official schedule before treating this as authoritative.')
            for start, title in games:
                game = dt.datetime.fromisoformat(start)
                print(f'{title}: {game:%Y-%m-%d %I:%M %p} Eastern')
                if input('Schedule playback for this game? [y/N] ').strip().lower() == 'y':
                    value = input(f'Start Eastern YYYY-MM-DD HH:MM [{game:%Y-%m-%d %H:%M}]: ').strip()
                    when = dt.datetime.strptime(value, '%Y-%m-%d %H:%M').replace(tzinfo=EASTERN) if value else game
                    schedule(when, args.volume)
                    print('This replaces the previous KBO-Alarm task.')
    except (Exception, KeyboardInterrupt) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
