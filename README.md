# Planfix Reminder

A desktop notification system for Planfix tasks with customizable toast notifications and intelligent reminder management.

![Python](https://img.shields.io/badge/python-3.7+-blue.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)

## Features

- Automatic task categorization (overdue, urgent, current)
- Custom toast notifications with interactive buttons
- Sound alerts for different task types
- Snooze functionality (15 minutes or 1 hour)
- Draggable notification windows
- Smart repeat reminders
- Direct task opening in browser
- Detailed statistics tracking

## Installation

### Requirements

- Python 3.7+
- Planfix API access
- tkinter (usually included with Python)

### Setup

1. Clone the repository:
```bash
git clone https://github.com/username/planfix-reminder.git
cd planfix-reminder
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure the application:
Create `config.ini` with your Planfix credentials:

```ini
[Planfix]
api_token = YOUR_API_TOKEN
account_url = https://your-account.planfix.com/rest

[Settings]
check_interval = 300
notify_current = true
notify_urgent = true
notify_overdue = true
```

4. Run the application:
```bash
python enhanced_planfix_reminder.py
```

## Configuration

### config.ini settings

| Parameter | Description | Default |
|-----------|-------------|---------|
| `api_token` | Planfix API token | - |
| `account_url` | REST API URL (must end with /rest) | - |
| `check_interval` | Task check interval in seconds | 300 |
| `notify_current` | Enable notifications for current tasks | true |
| `notify_urgent` | Enable notifications for urgent tasks | true |
| `notify_overdue` | Enable notifications for overdue tasks | true |

### Getting API Token

1. Log in to Planfix as administrator
2. Go to Settings → API
3. Create new API key
4. Copy the token to config.ini

## Notification Types

### Overdue Tasks
- Color: Red background
- Sound: 3 critical beeps
- Behavior: Stays until manually closed
- Auto-repeat: 5 minutes if accidentally closed

### Urgent Tasks
- Color: Orange background
- Sound: Warning beep
- Behavior: Stays until manually closed
- Auto-repeat: 15 minutes if accidentally closed

### Current Tasks
- Color: Blue background
- Sound: None
- Behavior: Stays until manually closed
- Auto-repeat: 30 minutes if accidentally closed

## Controls

### Notification Buttons
- **Open** - Opens task in browser
- **15min** - Snooze for 15 minutes
- **1h** - Snooze for 1 hour
- **Done** - Mark as viewed (won't show again)
- **✕** - Close (will reappear after delay)
- **📌** - Pin/unpin window

### Window Management
- Drag the title bar to move notifications
- Multiple notifications cascade automatically
- Notifications stay on top of other windows

## System Requirements

### Windows
- Windows 7+ 
- Python 3.7+ with tkinter
- winsound (included)

### Linux
```bash
# Ubuntu/Debian
sudo apt-get install python3-tk libnotify-bin

# CentOS/RHEL  
sudo yum install tkinter libnotify
```

### macOS
```bash
brew install python-tk terminal-notifier
```

## Project Structure

```
planfix-reminder/
├── enhanced_planfix_reminder.py  # Main application
├── config.ini                    # Configuration file
├── requirements.txt              # Python dependencies
└── README.md                     # Documentation
```

## Troubleshooting

### No notifications appearing
Check system notification permissions and verify API connection.

### API connection errors
1. Verify API token is correct
2. Ensure account_url ends with `/rest`
3. Check Planfix server availability

### No tasks showing
Verify user has permission to view assigned tasks.

### Import errors
Install missing dependencies:
```bash
pip install -r requirements.txt
```

## Development

The application uses:
- `requests` for Planfix API communication
- `tkinter` for GUI notifications
- `threading` for background task monitoring
- `plyer` as fallback for system notifications

### Key Components

- `PlanfixAPI` - Handles API communication
- `ToastNotification` - Custom notification windows
- `ToastManager` - Manages notification lifecycle
- `categorize_tasks()` - Task classification logic

## Dependencies

```
requests>=2.31.0
plyer>=2.1.0
python-dotenv>=1.0.0
```

## License

MIT License - see LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request