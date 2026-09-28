# insta-shadow-comment

Checks whether an account has commented on an Instagram post and, if so, shows the comment.
Comments are read one page at a time and the search stops as soon as the target comment is found:
nothing is saved to disk.

It can be used from a local web page or from the terminal.

## Requirements

- macOS or Linux with **Python 3.9+** (already installed on macOS: check with `python3 --version`)
- An Instagram account to log in with, **different** from the account whose comment you are
  looking for (the author of a comment always sees it, even when it is hidden from everyone else)

## Installation (one time only)

```bash
cd insta-shadow-comment
python3 -m venv .venv                     # create the project's virtual environment
source .venv/bin/activate                 # activate it (the prompt shows "(.venv)")
pip install -r requirements.txt           # install instaloader and flask
```

## Configuration

Copy the example file and open it in an editor:

```bash
cp config.example.ini config.ini
```

Fill in `username`, then **one** of the two login methods.

### Method 1 (recommended): browser cookies

Instagram often blocks password logins made by a script ("Checkpoint required").
Reusing your browser session avoids the problem.

1. Log in to https://www.instagram.com in your browser with the account you want to use.
2. Open the developer tools (**Cmd+Option+I**) and go to the cookies for `https://www.instagram.com`:
   - **Chrome**: *Application* tab → *Cookies*
   - **Safari**: *Storage* tab → *Cookies* (first enable the Develop menu in Settings → Advanced)
   - **Firefox**: *Storage* tab → *Cookies*
3. Copy the values of `sessionid` and `csrftoken` into `config.ini`:

```ini
[instagram]
username = your_username
sessionid = 1234567%3AAbCdEf...
csrftoken = xYz123...
password =
```

Do not log out from that browser: doing so also invalidates the session used by the tool.

### Method 2: password

Leave `sessionid` empty and fill in `password`. If you have two-factor authentication enabled,
the code is requested in the terminal at startup.

---

After the first successful start, the session is saved to `~/.config/instaloader/session-<username>`:
from then on, the login details in `config.ini` are no longer needed.
`config.ini` contains personal data: do not share it (it is already excluded in `.gitignore`).

## Running

Every time you open a new terminal, activate the environment first:

```bash
cd insta-shadow-comment
source .venv/bin/activate
```

### Web page

```bash
python app.py
```

Open **http://127.0.0.1:8000** in your browser, paste the **Post link**, type the
**Account to look for** and press **Search**. The post's author, date and caption are shown
first, so you can check it is the right post while the comments are being searched; the result
appears below. Available options:

- **Include replies**: also search among replies to comments
- **Find all of the account's comments**: do not stop at the first match

To stop the server press **Ctrl+C** in the terminal. The page is reachable only from your own computer.

### Terminal

```bash
python check_comment.py https://www.instagram.com/p/XXXXXXX/ account_to_find
python check_comment.py XXXXXXX account_to_find --all          # all of the account's comments
python check_comment.py XXXXXXX account_to_find --no-replies   # skip replies (faster)
```

## Reading the result

| Result | Meaning |
|---|---|
| Found | the comment is visible to other users |
| Found, marked **"hidden by Instagram"** | it is among the "hidden comments" (usually the offensive/spam filter) |
| Not found | it is not visible to others: deleted, hidden by the post's author (restricted account, hidden words, ...) or filtered by Instagram |

The comment count declared by the post is often higher than the number of comments scanned:
the difference is comments that Instagram does not show to viewers.

To tell whether the issue affects a single post or the account in general, try commenting on a
post by a different profile and check it with the tool.

## Common problems

| Message | What to do |
|---|---|
| `Missing configuration file` | create `config.ini` from `config.example.ini` |
| `Instagram blocked the scripted login` / `Checkpoint required` | use the browser cookie method |
| `The cookies in config.ini are invalid or expired` | copy `sessionid` and `csrftoken` from the browser again |
| `The session is no longer valid` | delete `~/.config/instaloader/session-<username>` and restart |
| `Instagram is rate-limiting requests` | wait a few minutes before trying again |
| `Address already in use` when starting `app.py` | another instance is already running: close it or change `PORT` in `app.py` |

## Project structure

```
app.py               web page (Flask)
templates/index.html page layout
check_comment.py     terminal version
instacheck.py        shared logic: configuration, login, reading comments
config.example.ini   configuration file template
requirements.txt     required libraries
```
