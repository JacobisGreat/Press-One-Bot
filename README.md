# Telegram Call Bot with SIP Integration

A Telegram bot that makes automated voice calls using SIP protocol with 2-stage audio scripts and digit collection.
- **Please leave a star if you want more updates, for assistance/feature requests message @highnotes on discord**


## Features

### 📞 Call Management
- **`/call`** - Upload CSV files to start call campaigns
- **`/recall`** - Automatically recall contacts who didn't press any digit during IVR
- Support for concurrent calls and rate limiting
- Real-time call status tracking

### 📝 Script Management
- **`/script`** - Create and manage call scripts
- Upload custom MP3 audio files for:
  - Opening message
  - After digit press response
- Switch between multiple scripts

### ⚙️ Settings
- **`/settings`** - Configure call parameters:
  - Concurrent calls (1-20)
  - Calls per second (0.1-10.0)
  - Custom caller ID
  - Active script selection

## Setup Instructions

### 1. Prerequisites

- Python 3.8+
- Telegram Bot Token (from @BotFather)
- SIP Provider/Server with:
  - SIP server hostname/IP
  - SIP username and password
  - Audio codec support (G.711/G.722)
  - Outbound calling capabilities
- Public webhook URL (ngrok, domain, etc.)

### 2. Installation

```bash
# Clone or download the project
cd call-campaign-bot

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Configuration

Create a `.env` file in the project directory:

```bash
cp config.env.example .env
```

Edit `.env` with your credentials:
```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
SIP_SERVER=your.sip.server.com
SIP_USERNAME=your_sip_username
SIP_PASSWORD=your_sip_password
SIP_PORT=5060
WEBHOOK_URL=https://your-domain.com
```

### 4. Webhook Setup

The bot requires a public webhook URL for SIP event callbacks. You can use:

#### Option A: ngrok (for testing)
```bash
# Install ngrok
brew install ngrok  # macOS
# or download from https://ngrok.com/

# In a separate terminal, run the webhook server
python webhook_server.py

# In another terminal, expose it with ngrok
ngrok http 5000

# Use the ngrok HTTPS URL in your .env file
WEBHOOK_URL=https://abc123.ngrok.io
```

#### Option B: Production Server
Deploy the webhook server (`webhook_server.py`) to a cloud platform and use that URL.

### 5. Run the Bot

```bash
# Start the webhook server (in one terminal)
python webhook_server.py

# Start the Telegram bot (in another terminal)
python bot.py
```

## Usage Guide

### CSV Format for Call Campaigns

The bot accepts CSV files with the following format:

```csv
name,email,phonenumber
John Doe,john@example.com,+1234567890
Jane Smith,jane@example.com,+9876543210
Bob Johnson,bob@example.com,+1122334455
```

**Required columns:** `name`, `phonenumber`
**Optional columns:** `email`

### Creating Call Scripts

1. Use `/script` command
2. Select "Create New Script"
3. Enter a script name
4. Upload opening audio file (MP3)
5. Upload after-digit-press audio file (MP3)

### Call Flow

1. **Opening**: Bot plays the opening audio
2. **IVR**: Waits for user to press any digit (10-second timeout)
3. **Response**: If digit pressed, plays after-digit audio
4. **Tracking**: Records which contacts pressed digits vs. those who didn't

### Recall Functionality

The `/recall` command will:
- Find all contacts from previous campaigns who didn't press any digit
- Reset their status to "pending"
- Start a new campaign with only those contacts

## Database Schema

The bot uses SQLite with the following tables:

- **contacts**: Store contact information and call status
- **scripts**: Store script definitions and audio file paths
- **settings**: Store user-specific settings
- **call_logs**: Log all call attempts and results

## SIP Configuration

### Required SIP Setup

1. **SIP Provider**: Choose a SIP provider (VoIP.ms, Flowroute, 3CX, etc.)
2. **Audio Codecs**: Ensure G.711 (PCMU/PCMA) support minimum
3. **DTMF Support**: In-band DTMF or RFC2833 for digit detection
4. **Firewall**: Open SIP port (5060) and RTP range (10000-20000)

### Webhook Endpoints

The bot exposes these endpoints for SIP events:

- `POST /sip_webhook` - Handle SIP call events
- `GET /health` - Health check
- `GET /sip_status` - SIP service status

## Troubleshooting

### Common Issues

1. **"No script available"**
   - Create a script using `/script` before starting campaigns
   - Ensure audio files are uploaded successfully

2. **Webhook errors**
   - Verify your webhook URL is publicly accessible
   - Check webhook server logs for errors
   - Ensure the webhook server is running

3. **Call failures**
   - Verify SIP credentials and server connectivity
   - Check phone number format (+1234567890)
   - Test SIP registration with your provider
   - Check firewall/NAT configuration

4. **CSV parsing errors**
   - Verify CSV has required columns: `name`, `phonenumber`
   - Check for proper CSV formatting
   - Ensure phone numbers include country code

### Logs

- Bot logs are displayed in the console
- Database operations are logged for debugging

## Security Considerations

- Never commit `.env` files to version control
- Use HTTPS for webhook URLs in production
- Implement rate limiting to prevent abuse
- Regularly backup the database

## Legal Compliance

**Important**: Ensure compliance with local regulations:

- Obtain proper consent before calling contacts
- Respect Do Not Call registries
- Include opt-out mechanisms in your scripts
- Follow TCPA, GDPR, and other applicable laws

## Support

For issues or questions:
1. Check the troubleshooting section
2. Check bot logs for error messages

## License

This project is provided as-is for educational and commercial use. Please ensure compliance with all applicable laws and regulations when using for commercial purposes. 
