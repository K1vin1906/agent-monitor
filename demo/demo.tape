# VHS recording for Agent Monitor TUI demo
Output demo/demo.gif

Set Shell "bash"
Set FontSize 12
Set Width 1100
Set Height 700
Set Theme "Catppuccin Mocha"
Set Padding 10
Set TypingSpeed 0ms

# Start socket server in background, then launch monitor
Hide
Type "cd ~/Projects/agent-monitor && python3 demo/simulate_events.py & sleep 2 && uv run python monitor.py"
Enter
Sleep 2
Show

Sleep 24s
