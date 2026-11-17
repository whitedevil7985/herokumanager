# GitHub ZIP Uploader Bot

Private Telegram bot for uploading ZIP contents to GitHub repositories. Each upload asks whether to use an existing repository or create a new one.

## Deploy on Heroku

1. Create a Heroku app and connect this repository.
2. Choose **Worker** as the process type. The included `Procfile` runs `python bot.py`.
3. Add the Config Vars below.
4. Scale the `worker` process to **1** (do not run multiple polling workers).

## Required Config Vars

| Key | Description |
| --- | --- |
| `API_ID` | Telegram API ID from my.telegram.org |
| `API_HASH` | Telegram API hash |
| `BOT_TOKEN` | Token from @BotFather |
| `OWNER_ID` | Your numeric Telegram user ID |
| `GITHUB_TOKEN` | GitHub fine-grained PAT |
| `GITHUB_OWNER` | GitHub username, e.g. whitedevil7985 |

Optional: `MAX_ZIP_MB` (40), `MAX_EXTRACTED_MB` (200), `MAX_FILES` (500).

## GitHub token permissions

For existing repositories, grant **Contents: Read and write** on the repositories you want to use. For creating repositories, grant **Administration: Read and write** for the account, plus Contents write access. Fine-grained token availability and account policies may limit repository creation; if creation is denied, use an existing repo or adjust the token permissions.

Never put the GitHub token in source code or commit it to this repository. Store it only in Heroku Config Vars.

## Telegram use

- Send `/start`, then send a ZIP document.
- Choose existing repository or new repository.
- For an existing repository, send `owner/repository`.
- For a new repository, send its name and choose public/private.
- Send a commit message to confirm the upload.
- `/repos`, `/status`, and `/cancel` are available.

## Safety and limits

The bot rejects path traversal, absolute paths, symlinks, duplicate paths, suspicious compression ratios, oversized archives, and excessive file counts. It uploads files as Git blobs, so binary files are supported. Pending upload state is held in memory and is cleared if the Heroku worker restarts. Avoid sending secrets inside ZIP files.
