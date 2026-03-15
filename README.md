
# Glance

## summary

A quick and dirty way to have a select few important notifications always visible e.g. emails,
code reviews, jira. This is so that you can remain deeply focused on the current task, whilst being
able to *glance* at what else might be waiting on you without having to context switch to email
clients, browsers etc.

Instructions are for windows at the moment.

## Usage
The repo is set up so you can keep tracked defaults in `config.toml` and personal settings in
`config.local.toml`. The local file is ignored, so your tokens, folder selections, and status
file path do not block `git pull`.

The quickest way to get started is:

```bat
scripts\run_glance.cmd
```

On first run that script will:
- copy `config.toml` to `config.local.toml` if needed
- copy `data\status.json` to `data\status.local.json` if needed
- start the renderer using `config.local.toml`

To refresh counts with the same local config:

```bat
scripts\update_status.cmd
```

If you prefer to run the Python entry points directly, they now look for `config.local.toml`
first and fall back to `config.toml`.

```bat
pythonw.exe "C:\path\to\glance.py" --config "C:\path\to\config.local.toml"
python.exe "C:\path\to\update_status.py" --config "C:\path\to\config.local.toml"
```
Use python.exe and not pythonw.exe if you are making sure that it's starting up and running fine
otherwise you have to kill the process from task manager or using taskkill.

### With Task Scheduler:
- Create a task that triggers on logon. Add a delay if you want.
- General: Set 'Run only when user is logged on'
- Action should be: Start a program `C:\Path\to\glance\scripts\run_glance.cmd`
- Settings: If the task is already running the the following rule applies:
  - 'Do not start a new instance'

## Design
- Always on top visibility without being obtrusive
- Read from some sort of status.json that a different background scrip/task will generate
  - simple format that has name, symbol, count/value and severity
  - fast to parse for potential use in a powershell prompt
