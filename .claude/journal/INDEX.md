# Journal — channel-z0

Newest first.

- [2026-08-24 Spawning the station on another machine, in one command](2026-08-24-spawn-a-station-on-another-machine.md) — branch agent/z0-spawn-automation; /iptv/channel/1.ts is a 404 (the channel is 0), the latest-nvidia tag is abandoned upstream so a fresh node loses the graphics engine, there is no ErsatzTV config API so the database IS the station, and the playout anchor is an instruction index that must be cleared or the week resumes mid-block
- [2026-08-20 LUNCH LOOPS: a real audio visualiser, and a different form each day](2026-08-20-lunch-loops-visualiser-and-day-themes.md) — PR #41; astats prints only at INFO so -v error yields a visualiser that never moves, sqlite3 CREATES the db file you typo, a playlist may not name the same source twice, and nulling LastScan does not force a scan
- [2026-08-19 L-system station intervals, drawn and glitched by their own source](2026-08-19-lsystem-intervals.md) — PR #37; comparing the two bitstreams does not prove ffedit did anything, MV amplitudes under ~1 half-pel round away to nothing, and numpy in LXC 111 is broken
- [2026-08-15 drawtext ate punctuation on proxy placeholder cards](2026-08-15-drawtext-proxy-card-text.md) — PR #31; #15 was already merged and skipped make-proxies.sh; a second EXIT trap replaces the first
