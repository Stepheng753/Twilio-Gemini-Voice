import os
import json
import base64
import asyncio
from fastapi import FastAPI, WebSocket, Request, Response
from dotenv import load_dotenv
import websockets

try:
    import audioop
except ImportError:
    # Python 3.13+ requires audioop-lts
    import audioop

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable not set in .env")

HOST = "generativelanguage.googleapis.com"
MODEL = "models/gemini-2.5-flash-native-audio-latest"
GEMINI_WS_URL = f"wss://{HOST}/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent?key={GEMINI_API_KEY}"

app = FastAPI()

@app.get("/")
async def index():
    return {"message": "Twilio-Gemini Voice Integration Running!"}

@app.api_route("/twiml", methods=["GET", "POST"])
async def twiml(request: Request):
    """
    Twilio webhook endpoint. Returns TwiML to connect the call to our WebSocket.
    """
    host = request.headers.get("host", "dev.stepheng753.com")
    
    # Check if Nginx is proxying HTTPS
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    ws_scheme = "wss" if scheme == "https" else "ws"
    
    wss_url = f"{ws_scheme}://{host}/media"
    
    twiml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{wss_url}" />
    </Connect>
</Response>"""
    return Response(content=twiml_response, media_type="text/xml")

@app.websocket("/media")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("[Twilio] Connected to /media")
    stream_sid = None

    try:
        # Connect to Gemini Multimodal Live API
        async with websockets.connect(GEMINI_WS_URL) as gemini_ws:
            print("[Gemini] Connected")
            
            # Send Initial Setup Message
            setup_msg = {
                "setup": {
                    "model": MODEL,
                    "generationConfig": {
                        "responseModalities": ["AUDIO"],
                        "speechConfig": {
                            "voiceConfig": {
                                "prebuiltVoiceConfig": {
                                    "voiceName": "Puck"
                                }
                            }
                        }
                    }
                }
            }
            await gemini_ws.send(json.dumps(setup_msg))
            
            raw_response = await gemini_ws.recv()
            print("[Gemini] Setup response:", json.loads(raw_response))

            async def receive_from_twilio():
                nonlocal stream_sid
                try:
                    while True:
                        data = await websocket.receive_text()
                        msg = json.loads(data)
                        event = msg.get("event")
                        
                        if event == "start":
                            stream_sid = msg["start"]["streamSid"]
                            print(f"[Twilio] Stream started: {stream_sid}")
                            
                            # Optional: Send an initial prompt to Gemini to start the conversation
                            client_content = {
                                "clientContent": {
                                    "turns": [{
                                        "role": "user",
                                        "parts": [{"text": "Say hello to the caller and ask how you can help."}]
                                    }],
                                    "turnComplete": True
                                }
                            }
                            await gemini_ws.send(json.dumps(client_content))

                        elif event == "media":
                            payload = msg["media"]["payload"]
                            
                            # Decode Twilio's base64 mu-law (8kHz)
                            mulaw_data = base64.b64decode(payload)
                            
                            # Convert mu-law to PCM 16-bit
                            pcm_data = audioop.ulaw2lin(mulaw_data, 2)
                            
                            # Resample 8000Hz -> 16000Hz for Gemini
                            pcm16_data, _ = audioop.ratecv(pcm_data, 2, 1, 8000, 16000, None)
                            
                            # Send real-time audio chunk to Gemini
                            realtime_input = {
                                "realtimeInput": {
                                    "mediaChunks": [{
                                        "mimeType": "audio/pcm;rate=16000",
                                        "data": base64.b64encode(pcm16_data).decode("utf-8")
                                    }]
                                }
                            }
                            await gemini_ws.send(json.dumps(realtime_input))
                            
                        elif event == "stop":
                            print("[Twilio] Stream stopped.")
                            break
                            
                except Exception as e:
                    print(f"[Twilio] Closed/Error: {e}")

            async def receive_from_gemini():
                try:
                    while True:
                        response_raw = await gemini_ws.recv()
                        response = json.loads(response_raw)
                        
                        server_content = response.get("serverContent")
                        if server_content:
                            model_turn = server_content.get("modelTurn")
                            if model_turn:
                                for part in model_turn.get("parts", []):
                                    inline_data = part.get("inlineData")
                                    if inline_data:
                                        mime_type = inline_data.get("mimeType", "")
                                        b64_data = inline_data.get("data", "")
                                        if b64_data and mime_type.startswith("audio/pcm"):
                                            
                                            # Gemini typically returns 24kHz PCM
                                            pcm_data = base64.b64decode(b64_data)
                                            
                                            # Resample 24kHz -> 8kHz
                                            pcm8_data, _ = audioop.ratecv(pcm_data, 2, 1, 24000, 8000, None)
                                            
                                            # Convert PCM 16-bit back to mu-law 8-bit
                                            mulaw_data = audioop.lin2ulaw(pcm8_data, 2)
                                            
                                            if stream_sid:
                                                twilio_msg = {
                                                    "event": "media",
                                                    "streamSid": stream_sid,
                                                    "media": {
                                                        "payload": base64.b64encode(mulaw_data).decode("utf-8")
                                                    }
                                                }
                                                await websocket.send_text(json.dumps(twilio_msg))
                                                
                except Exception as e:
                    print(f"[Gemini] Closed/Error: {e}")

            # Run concurrently
            twilio_task = asyncio.create_task(receive_from_twilio())
            gemini_task = asyncio.create_task(receive_from_gemini())
            
            # Wait for either to finish
            done, pending = await asyncio.wait(
                [twilio_task, gemini_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            for p in pending:
                p.cancel()
                
    except Exception as e:
        import logging
        logging.error(f"FATAL ERROR IN WEBSOCKET: {e}", exc_info=True)
