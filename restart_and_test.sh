#!/bin/bash
# Script to restart the server and test the RDL fix

echo "=========================================================================="
echo "SSRS RDL Generator - Server Restart & Test"
echo "=========================================================================="
echo ""

echo "📋 Instructions:"
echo "  1. Stop the current server if running (Ctrl+C)"
echo "  2. Run this script: bash restart_and_test.sh"
echo ""

read -p "Press Enter to start the server with auto-reload enabled..."

echo ""
echo "🚀 Starting server with --reload flag..."
echo "   (Code changes will automatically reload)"
echo ""

cd /Users/mohammadsmadi/backend

# Start server with reload
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Note: This will run in foreground. Press Ctrl+C to stop.
