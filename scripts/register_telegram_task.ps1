# Registers a Windows Scheduled Task that runs the morning refresh + Telegram
# daily-movers alert every weekday at 9:30am. If the laptop is off/asleep at
# 9:30, StartWhenAvailable runs it as soon as you next log in.
#
# Run ONCE, in PowerShell:
#   powershell -ExecutionPolicy Bypass -File "scripts\register_telegram_task.ps1"

$bat = "C:\Users\shashirekha\OneDrive - Microsoft\Shashi\Dashboard\Dashboard\bat\morning_refresh.bat"

$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$bat`""

# Weekday trigger at 9:30am (Mon-Fri).
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 9:30am

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -WakeToRun `
    -DontStopOnIdleEnd `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName "STT Morning Movers Alert" `
    -Description "Refreshes prices and sends the daily Mov(D) movers to Telegram (weekdays 9:30am, or earliest login)." `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Force

Write-Host "Task 'STT Morning Movers Alert' registered. Trigger: Mon-Fri 09:30 (runs at next login if missed)."
Write-Host "Test it now with:  Start-ScheduledTask -TaskName 'STT Morning Movers Alert'"
