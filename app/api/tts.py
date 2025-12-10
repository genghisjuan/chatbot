"""
Text-to-Speech API endpoint using OpenAI TTS.

This endpoint converts text to natural-sounding speech using OpenAI's TTS API.
It returns MP3 audio that can be played directly in the browser.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from openai import OpenAI
from app.core.config import settings
from app.services import logger

router = APIRouter()

# Validate API key at module load time
if not settings.OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not configured in settings")

# Singleton OpenAI client (reused across requests)
client = OpenAI(api_key=settings.OPENAI_API_KEY)


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4096, description="Text to convert to speech (max 4096 chars)")
    voice: str = Field(
        default="nova", 
        pattern="^(alloy|echo|fable|onyx|nova|shimmer)$",
        description="Voice to use for speech generation"
    )


@router.post("/tts")
async def text_to_speech(request: TTSRequest):
    """
    Convert text to speech using OpenAI TTS.
    
    Returns MP3 audio as binary response.
    """
    try:
        response = client.audio.speech.create(
            model="tts-1",  # Use tts-1 for speed, tts-1-hd for quality
            voice=request.voice,
            input=request.text,
            response_format="mp3"
        )
        
        # Get the audio bytes
        audio_bytes = response.content
        
        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={"Content-Disposition": "inline; filename=speech.mp3"}
        )
        
    except Exception as e:
        logger.error(f"TTS generation failed for text length {len(request.text)}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate speech")

