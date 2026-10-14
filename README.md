# KBO Alarm

Local Windows CLI that schedules a wake timer and attempts to play a live **Doosan** game on SOOP from `kbo_global1`–`kbo_global5`. No frontend, conventional alarm, or automatic stop time. Uses Eastern local time (`America/New_York`, including daylight saving).

**Status:** schedule parsing and timezone conversion are tested with fixtures. Windows wake, audio control, official KBO discovery, and SOOP automation still require a laptop test. The development cloud fetched both sites’ HTML, but browser validation was blocked by proxy certificate trust: the injected proxy CA collides with an existing NSS certificate (same issuer and serial, different public key). The attempted approved repair was rolled back and original trust settings were verified. A clean, platform-supported browser trust configuration is needed for cloud browser validation. This is not yet a verified overnight alarm. No game on October 14 has been independently confirmed.

## Install on your Windows laptop

Install Python 3.11+ and Microsoft Edge. Open PowerShell in this repository:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe kbo_alarm.py --help
```

Playwright uses installed Edge; no separate browser download required. Keep the repository and virtual environment at the same location after scheduling.

## First: verify immediate playback and wake

```powershell
.\.venv\Scripts\python.exe kbo_alarm.py play --volume 60
```

This opens Edge with its own persistent profile. If SOOP asks for consent or sign-in, complete it in that browser. It searches `doosan`, requires the title and exact official channel in the same result link, and attempts playback. It retries for up to 45 minutes if no matching stream appears. Never substitutes another team's stream. It does not bypass subscriptions, regional restrictions, or access controls. Close the browser to stop. Logs and the latest failure screenshot are under `%LOCALAPPDATA%\KBO-Alarm`.

If the search UI or result cards differ from the assumed structure, automation will fail safely; inspect the screenshot and report the failure rather than relying on this overnight.

Keep the laptop plugged in with its lid open. In Windows Power Options → Advanced settings → Sleep → Allow wake timers, enable wake timers while plugged in. Under Settings → Accounts → Sign-in options, set the sign-in requirement after sleep to **Never**, if your Windows version and policy allow it. Stay signed in. The task uses your interactive session; it cannot unlock Windows. Leaving a session unlocked allows physical access, so choose this only in an appropriate location. You do not need to delete your password.

Select the laptop speakers as the default output and disconnect headphones/Bluetooth audio. The script unmutes the default Windows audio endpoint, sets its volume, and unmutes the web video; per-app mixer muting or the wrong output device can still prevent audible sound.

```powershell
.\.venv\Scripts\python.exe kbo_alarm.py wake-test --minutes 3 --volume 60
```

Then select **Sleep**, not Shut down. Confirm that it wakes, opens Edge, and, if a Doosan stream is live, plays audibly. If no game is live, wake/browser startup can be checked, but this does not validate game playback. Some Modern Standby hardware does not honor wake timers; if the test fails, use the supported fallback of keeping the laptop awake while plugged in with its display off. Do not assume an untested wake timer works.

## Schedule October 14, 2026 at 5:30 a.m. Eastern

```powershell
.\.venv\Scripts\python.exe kbo_alarm.py schedule --at "2026-10-14 05:30" --volume 60
```

The CLI rejects past times. Change the date/time and volume whenever needed. Each command replaces the single `KBO-Alarm` task. Windows Task Scheduler converts Eastern time to the machine's local timezone, wakes the computer at that time, and starts playback in the signed-in session. If the task is missed, Windows may run it later when available. Check Task Scheduler's next-run time before bed. Playback keeps Windows awake while it runs; you manually close the browser when finished.

## Discover upcoming games and choose an alarm

```powershell
.\.venv\Scripts\python.exe kbo_alarm.py games --days 7 --volume 60
```

Loads the official KBO schedule, scans available series including postseason, converts Korea times to Eastern, filters strictly for Doosan matchups, and excludes cancellations. For each upcoming game it asks whether to schedule and which Eastern date/time to start. It runs on demand, including next season; it is not a continuously running notification service. Scheduling another game replaces the previous alarm. A zero-result discovery is not proof there are no games if the source layout changes.

```powershell
.\.venv\Scripts\python.exe kbo_alarm.py cancel
schtasks /Delete /TN KBO-Alarm-Test /F
```

## Development checks

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Five tests cover Doosan filtering, cancellations, duplicate rows, timezone conversion, and generated wake-task configuration. No Windows task is registered by the test suite. Linux/cloud supports parser development only; Windows scheduling and audible browser playback must be validated locally.
