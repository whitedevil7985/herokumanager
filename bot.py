import base64, io, os, re, zipfile
from pathlib import PurePosixPath

import httpx
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import API_ID, API_HASH, BOT_TOKEN, OWNER_ID, GITHUB_TOKEN, GITHUB_OWNER, MAX_ZIP_MB, MAX_EXTRACTED_MB, MAX_FILES

required = (API_ID, API_HASH, BOT_TOKEN, OWNER_ID, GITHUB_TOKEN, GITHUB_OWNER)
if not all(required):
    raise RuntimeError("Missing required Heroku Config Vars. See README.md.")

app = Client("github_zip_uploader", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
API = "https://api.github.com"
HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
pending = {}

def owner_filter(_, __, update):
    user = getattr(update, "from_user", None)
    return bool(user and user.id == OWNER_ID)

OWNER = filters.create(owner_filter)

async def gh(method, path, **kwargs):
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.request(method, API + path, headers=HEADERS, **kwargs)
    if response.status_code >= 400:
        try:
            detail = response.json().get("message", response.text)
        except Exception:
            detail = response.text
        raise RuntimeError(f"GitHub API {response.status_code}: {detail}")
    return response.json() if response.content else {}

def parse_zip(raw):
    if len(raw) > MAX_ZIP_MB * 1024 * 1024:
        raise ValueError(f"ZIP size limit is {MAX_ZIP_MB} MB.")
    entries, total = [], 0
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        files = [item for item in archive.infolist() if not item.is_dir()]
        if not files:
            raise ValueError("ZIP contains no files.")
        if len(files) > MAX_FILES:
            raise ValueError(f"Too many files. Limit: {MAX_FILES}.")
        seen = set()
        for item in files:
            name = item.filename.replace("\\", "/")
            path = PurePosixPath(name)
            mode = (item.external_attr >> 16) & 0o170000
            if path.is_absolute() or ".." in path.parts or not path.parts or name.startswith("/") or re.match(r"^[A-Za-z]:", name) or mode == 0o120000:
                raise ValueError(f"Unsafe ZIP entry: {name}")
            clean = str(path)
            if clean in seen:
                raise ValueError(f"Duplicate path in ZIP: {clean}")
            seen.add(clean)
            total += item.file_size
            if total > MAX_EXTRACTED_MB * 1024 * 1024:
                raise ValueError(f"Extracted size exceeds {MAX_EXTRACTED_MB} MB.")
            if item.file_size and not item.compress_size:
                raise ValueError("Invalid compressed ZIP entry.")
            if item.compress_size and item.file_size / item.compress_size > 200:
                raise ValueError(f"Suspicious compression ratio: {clean}")
            entries.append((clean, archive.read(item)))
    return entries

async def create_repo(name, private):
    return await gh("POST", "/user/repos", json={
        "name": name, "private": private,
        "auto_init": True, "description": "Files uploaded with GitHub ZIP Uploader"
    })

async def commit_entries(repo, branch, entries, message):
    owner, name = repo.split("/", 1)
    ref = await gh("GET", f"/repos/{owner}/{name}/git/ref/heads/{branch}")
    parent_sha = ref["object"]["sha"]
    parent = await gh("GET", f"/repos/{owner}/{name}/git/commits/{parent_sha}")
    base_tree = parent["tree"]["sha"]
    tree_items = []
    for path, content in entries:
        blob = await gh("POST", f"/repos/{owner}/{name}/git/blobs", json={
            "content": base64.b64encode(content).decode("ascii"),
            "encoding": "base64",
        })
        tree_items.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
    tree = await gh("POST", f"/repos/{owner}/{name}/git/trees", json={
        "base_tree": base_tree, "tree": tree_items
    })
    commit = await gh("POST", f"/repos/{owner}/{name}/git/commits", json={
        "message": message, "tree": tree["sha"], "parents": [parent_sha]
    })
    await gh("PATCH", f"/repos/{owner}/{name}/git/refs/heads/{branch}", json={
        "sha": commit["sha"], "force": False
    })
    return commit["html_url"]

async def ask_commit(message, state):
    state["phase"] = "commit"
    await message.reply_text(
        f"Repository: `{state['repo']}`\nBranch: `{state['branch']}`\n"
        f"Files: `{len(state['entries'])}`\n\nCommit message bhejo."
    )

@app.on_message(filters.command("start") & OWNER)
async def start(_, message):
    await message.reply_text(
        "👋 **GitHub ZIP Uploader**\n\n"
        "ZIP document bhejo. Bot har baar poochhega ki existing repo mein upload karna hai ya naya repo banana hai.\n\n"
        "/upload — upload instructions\n/repos — repositories list\n/status — bot status\n/cancel — cancel current task"
    )

@app.on_message(filters.command("upload") & OWNER)
async def upload_help(_, message):
    await message.reply_text("Apni ZIP file Telegram par **Document** ke roop mein bhejo.")

@app.on_message(filters.command("status") & OWNER)
async def status(_, message):
    await message.reply_text(
        f"✅ Uploader ready\nGitHub account: `{GITHUB_OWNER}`\n"
        f"ZIP limit: {MAX_ZIP_MB} MB\nExtracted limit: {MAX_EXTRACTED_MB} MB\n"
        f"File limit: {MAX_FILES}"
    )

@app.on_message(filters.command("cancel") & OWNER)
async def cancel(_, message):
    pending.pop(message.from_user.id, None)
    await message.reply_text("❎ Current operation cancelled.")

@app.on_message(filters.command("repos") & OWNER)
async def repos(_, message):
    try:
        data = await gh("GET", "/user/repos?per_page=100&sort=updated&affiliation=owner,collaborator,organization_member")
        lines = [f"• `{r['full_name']}` — {r['visibility']}" for r in data[:60]]
        await message.reply_text("**Accessible repositories:**\n" + ("\n".join(lines) if lines else "No repositories found."))
    except Exception as exc:
        await message.reply_text(f"❌ {exc}")

@app.on_message(filters.document & OWNER)
async def receive_zip(_, message):
    document = message.document
    if not (document.file_name or "").lower().endswith(".zip"):
        await message.reply_text("Please ZIP file bhejo.")
        return
    if document.file_size and document.file_size > MAX_ZIP_MB * 1024 * 1024:
        await message.reply_text(f"ZIP limit {MAX_ZIP_MB} MB hai.")
        return
    status_message = await message.reply_text("⏳ ZIP download aur validation ho rahi hai...")
    try:
        data = await app.download_media(document, in_memory=True)
        entries = parse_zip(data.getvalue() if hasattr(data, "getvalue") else data)
        pending[message.from_user.id] = {"entries": entries, "filename": document.file_name}
        await status_message.edit_text(
            f"✅ ZIP ready — {len(entries)} files.\nUpload destination choose karo:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📁 Existing repository", callback_data="dest:existing"),
                InlineKeyboardButton("🆕 New repository", callback_data="dest:new"),
            ], [InlineKeyboardButton("Cancel", callback_data="cancel")]])
        )
    except Exception as exc:
        await status_message.edit_text(f"❌ ZIP error: {exc}")

@app.on_callback_query(OWNER)
async def callbacks(_, query):
    user_id = query.from_user.id
    state = pending.get(user_id)
    if query.data == "cancel":
        pending.pop(user_id, None)
        await query.message.edit_text("Upload cancelled.")
        await query.answer()
        return
    if not state:
        await query.answer("Pending ZIP nahi mili. ZIP dobara bhejo.", show_alert=True)
        return
    try:
        if query.data == "dest:existing":
            state["phase"] = "existing_repo"
            await query.message.edit_text("Repository ka full name bhejo. Example: `whitedevil7985/herokumanager`")
        elif query.data == "dest:new":
            state["phase"] = "new_repo"
            await query.message.edit_text("Naye repository ka naam bhejo. Example: `my-uploaded-project`")
        elif query.data == "visibility:public":
            state["private"] = False
            repo = await create_repo(state["repo_name"], False)
            state["repo"] = repo["full_name"]
            state["branch"] = repo["default_branch"]
            await ask_commit(query.message, state)
        elif query.data == "visibility:private":
            state["private"] = True
            repo = await create_repo(state["repo_name"], True)
            state["repo"] = repo["full_name"]
            state["branch"] = repo["default_branch"]
            await ask_commit(query.message, state)
        else:
            await query.answer("Unknown action.")
            return
        await query.answer()
    except Exception as exc:
        await query.message.reply_text(f"❌ {exc}")
        await query.answer()

@app.on_message(filters.text & ~filters.command(["start", "upload", "status", "cancel", "repos"]) & OWNER)
async def text_steps(_, message):
    state = pending.get(message.from_user.id)
    if not state:
        return
    text = message.text.strip()
    try:
        if state.get("phase") == "existing_repo":
            repo = text.removeprefix("https://github.com/").strip("/")
            if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
                await message.reply_text("Valid `owner/repository` bhejo.")
                return
            meta = await gh("GET", f"/repos/{repo}")
            if meta.get("archived"):
                await message.reply_text("Archived repository mein upload nahi kar sakte.")
                return
            state["repo"] = meta["full_name"]
            state["branch"] = meta["default_branch"]
            await ask_commit(message, state)
        elif state.get("phase") == "new_repo":
            if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", text):
                await message.reply_text("Repository name invalid hai. Dobara bhejo.")
                return
            state["repo_name"] = text
            state["phase"] = "visibility"
            await message.reply_text(
                f"New repo: `{GITHUB_OWNER}/{text}`\nVisibility choose karo:",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🌐 Public", callback_data="visibility:public"),
                    InlineKeyboardButton("🔒 Private", callback_data="visibility:private"),
                ]])
            )
        elif state.get("phase") == "commit":
            if len(text) > 200:
                await message.reply_text("Commit message 200 characters se chhota rakho.")
                return
            if not text:
                await message.reply_text("Commit message empty nahi ho sakta.")
                return
            progress = await message.reply_text("⏳ GitHub par files commit ho rahi hain...")
            url = await commit_entries(state["repo"], state["branch"], state["entries"], text)
            pending.pop(message.from_user.id, None)
            await progress.edit_text(f"✅ **Upload successful!**\n\nRepository: `{state['repo']}`\nFiles: `{len(state['entries'])}`\n[Open commit]({url})", disable_web_page_preview=True)
    except Exception as exc:
        await message.reply_text(f"❌ {exc}\nAgar issue resolve ho jaye to step dobara try karo, ya /cancel bhejo.")

@app.on_message(filters.all & ~OWNER)
async def deny(_, message):
    if getattr(message, "from_user", None):
        await message.reply_text("🔒 This bot is private.")
        
if __name__ == "__main__":
    app.run()
