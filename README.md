
# Glance

## summary

A quick and dirty way to have a select few important notifications always visible e.g. emails,
code reviews, jira. This is so that you can remain deeply focused on the current task, whilst being
able to *glance* at what else might be waiting on you without having to context switch to email
clients, browsers etc.

Instructions are for windows at the moment.

## Usage
To be used to read a status.json file that a different background task will create. This is to
keep things efficient and snappy. Means that I can use the status.json file for my terminal
prompt too.

```
pythonw.exe "C:\path\to\glance.py" -p "C:\path\to\status.json"
```
Use python.exe and not pythonw.exe if you are making sure that it's starting up and running fine
otherwise you have to kill the process from task manager or using taskkill.

### With Task Scheduler:
- Create a task that triggers on logon. Add a delay if you want.
- General: Set 'Run only when user is logged on'
- Action should be: Start a program C:\Path\to\glance\run_glance.cmd
- Settings: If the task is already running the the following rule applies:
  - 'Do not start a new instance'

## Design
- Always on top visibility without being obtrusive
- Read from some sort of status.json that a different background scrip/task will generate
  - simple format that has name, symbol, count/value and severity
  - fast to parse for potential use in a powershell prompt
