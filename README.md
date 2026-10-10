# 블로그 검색노출 진단·색인요청 도우미

Windows GUI that collects URLs from direct input, a sitemap, or a Blogspot feed, inspects each URL in Google Search Console, records per-URL history, resumes unfinished runs, and creates a local HTML report.

## Run

1. Install 64-bit Python 3.10 or newer and Google Chrome.
2. In this folder, run: py -m pip install -r requirements.txt
3. Run: py main.py
4. Enter the exact URL-prefix property (for example https://example.com/) or a domain property (sc-domain:example.com) and URLs to inspect.
5. Click “URL 가져오기 및 진단 시작”. The app collects URLs and prepares a dedicated connected Chrome automatically. If the profile is signed out, sign in, select the matching Search Console property, then click “중단 작업 이어하기”. The separate browser button remains available when you want to sign in before starting.
   Every click of the start button creates a fresh inspection run for the collected URLs, even if they were inspected recently. The resume button is only for unfinished runs. The request cooldown applies only to repeated indexing requests.
6. Review the report and app log. Indexing requests are disabled by default. Enable them only when you want the tool to click a request action for eligible results.

Google decides whether a URL is indexed; a request only asks Google to recrawl and does not guarantee inclusion. The actual request quota is controlled by Google, not this app. The local daily limit is a user-selected safety cap, and the app stops if it sees a quota warning.

## Data and recovery

The app writes under %LOCALAPPDATA%\SearchConsoleTool by default:

* data/history.sqlite3: URL state, request attempts, and resumable queue
* data/settings.json: app options
* chrome_profile/: dedicated Chrome profile and sign-in session
* reports/, logs/, screenshots/

A stopped or interrupted URL remains queued and can be resumed from the app. No history database, report, settings file, OAuth credential, or Chrome profile is bundled with a release.

The connected Chrome profile contains session cookies. Protect the Windows account and sign out or delete the chrome_profile folder if you no longer want to retain that session. The app does not ask for or store a Google password. The app binds remote debugging to localhost only and does not copy cookies from the regular Chrome profile.

Ordinary Chrome windows launched without remote debugging cannot be attached to after they have started. Chrome 136 and newer also reject remote debugging against the default Chrome data directory. This app therefore reuses a Chrome profile dedicated to this tool; it preserves the tool's prior sign-in session while keeping the regular profile separate.

The app selects an available loopback-only debugging port instead of assuming port 9222. It remembers that port only for the dedicated app profile and never attaches to an unrelated debugging Chrome instance.

## Build

Run `build_release.bat` on Windows 10 or 11. It builds `SearchConsoleHelper.exe` and creates `release/SearchConsoleHelper_Windows.zip` containing only the EXE and public documentation. Databases, reports, settings, OAuth files, and Chrome profiles are excluded. Build-script paths and commands use ASCII-only names to avoid Windows command-shell encoding failures.

## Layout

main.py starts the GUI. gui/ contains the window and worker queue integration, automation/ collects URLs and drives Search Console, core/ normalizes URLs and applies conservative status/request rules, storage/ manages settings and SQLite history/migration, and reports/ creates the HTML report.

Search Console changes its interface over time. Selector and message changes can require an update; unknown or ambiguous status text is deliberately not eligible for automatic requests.
