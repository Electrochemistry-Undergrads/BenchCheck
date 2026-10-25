# HackTX 2026 submission checks

Official sources checked on October 25, 2026:
- [HackTX requirements and sponsor tracks](https://hacktx26.devpost.com/)
- [HackTX competition and AI rules](https://hacktx26.devpost.com/rules)

## Requirements to verify before submitting

- Build during the October 24–25 hacking period; stop substantial changes at the cutoff. Devpost displays the submission deadline as **October 25, 11:30 a.m. CDT**. The requirements paragraph calls the zone CST; ask organizers if that discrepancy matters.
- Submit the project and a demonstration video to Devpost before the deadline.
- Team size: 1–4; team members must attend judging in person. The event page lists college students, ages 18+, US only. Confirm each participant's eligibility and active participation.
- Keep code and the video public, including after the event for prize eligibility.
- Disclose AI coding tools honestly in the submission and to judges. This project used **Anthropic Claude Code** and **OpenAI Codex**, with their contributions described in `DEVPOST.md`.
- Follow the MLH Code of Conduct and originality rules. Libraries and frameworks are allowed; previous project code or materials cannot be reused as new hackathon work. Preserve the real commit history.
- The SerpApi track requires meaningful use of SerpApi. BenchCheck uses Google Scholar search and Extract to connect measured features to quoted passages, condition comparisons, and next-check ranking.

## Project actions still requiring completion or confirmation

- **Repository visibility:** it was private when inspected. Make the reviewed repository public before submission; first ensure the complete history contains no secrets or unpublished lab data. `.env` remains ignored and must never be committed.
- **Video and submission:** record the current app, test public access, include the link in Devpost, select the intended tracks, and submit. No video or submission was created by this frontend update.
- **Team and timing:** confirm eligibility, attendance, team roster, and that all project work fits the official window. The code cannot verify these facts.
- **Evidence:** review the live/cached responses and judge whether each passage supports its attached hypothesis. Automated substring checks cannot establish scientific support.
- **Personal story:** replace draft placeholders only with true experiences. Claim only results that were actually measured.

The frontend intentionally has no example picker. Synthetic test data remain available as repository fixtures. Their explicit SYNTHETIC file comment automatically labels the analysis and exported reports. This change does not certify the entire submission or alter repository visibility.
