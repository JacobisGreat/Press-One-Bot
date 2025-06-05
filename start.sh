#!/bin/bash

# Start the Call Campaign Bot
echo "Starting Call Campaign Bot..."

# Check if .env file exists
if [ ! -f .env ]; then
    echo "Error: .env file not found!"
    echo "Please copy config.env.example to .env and fill in your credentials."
    exit 1
fi

# Create audio directory if it doesn't exist
mkdir -p audio

# Start webhook server in background
echo "Starting webhook server..."
python webhook_server.py &
WEBHOOK_PID=$!

# Wait a moment for webhook server to start
sleep 2

# Start Telegram bot
echo "Starting Telegram bot..."
python bot.py &
BOT_PID=$!

# Function to handle cleanup
cleanup() {
    echo "Shutting down..."
    kill $WEBHOOK_PID 2>/dev/null
    kill $BOT_PID 2>/dev/null
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

# Wait for both processes
wait $WEBHOOK_PID
wait $BOT_PID 