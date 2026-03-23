# Twilio + Gemini 2.5 Flash Voice Integration

This is a FastAPI Python application that uses WebSockets to connect a live Twilio phone call to the Google Gemini 2.5 Flash Multimodal Live API.

## Requirements

The project uses Python >= 3.9. 
Dependencies:
- `fastapi`
- `uvicorn`
- `websockets`
- `python-dotenv`
- `audioop-lts` (needed for Python 3.13+)

## Setup

1. **Navigate to this directory**:
   ```bash
   cd /home/stepheng753/Development/BackendServer/Twilio-Gemini-Voice
   ```

2. **Create a Python Virtual Environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Verify Environment Variables**:
   Ensure the `.env` file exists in this directory and has your `GEMINI_API_KEY`:
   ```env
   GEMINI_API_KEY=AIzaSy...
   ```

## Configure Twilio

1. Go to the [Twilio Console](https://console.twilio.com/) -> Phone Numbers -> Manage -> Active numbers.
2. Select the phone number you want to use.
3. Under "Routing" or "Voice Configuration", find the **"A call comes in"** setting.
4. Set it to **Webhook** and point it to your domain's `/twiml` endpoint:
   - `https://dev.stepheng753.com/twiml`
5. Select **HTTP POST** and save.

## Run the Server

Your Nginx server is currently configured to proxy all traffic for `dev.stepheng753.com` to a Unix socket: `/tmp/dev_stepheng753_com_api.sock`. Nginx is already perfectly configured to pass WebSocket headers!

1. Make sure your previous Flask app is not currently running and bound to that same socket. If it is, stop it.
2. Run this FastAPI server using Uvicorn bound to that exact socket:
   ```bash
   # Make sure the virtual environment is activated
   uvicorn app:app --uds /tmp/dev_stepheng753_com_api.sock
   ```

*Note: Depending on permissions, you may need to ensure Nginx can read/write to this socket file. If you encounter a 502 Bad Gateway, check socket permissions or simply run `chmod 666 /tmp/dev_stepheng753_com_api.sock`.*

Once running:
- Call your Twilio phone number.
- Twilio will request the TwiML from `https://dev.stepheng753.com/twiml`.
- Our server will respond with an instruction to open a WebSocket to `wss://dev.stepheng753.com/media`.
- Once connected, start speaking, and Gemini 2.5 Flash will talk back to you!
