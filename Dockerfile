FROM ghcr.io/astral-sh/uv:debian

WORKDIR /app

# Install system dependencies for audio decoding (libsndfile & ffmpeg for MP3, FLAC, OGG, M4A, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency specifications first for layer caching
COPY ./pyproject.toml .
COPY ./uv.lock .
COPY ./README.md .
COPY ./.python-version .

# Install production dependencies only into uv environment
RUN uv sync --no-install-project --no-dev

# Copy package source
COPY ./pocket_tts ./pocket_tts

# Install project package into virtualenv
RUN uv sync --no-dev

# Create persistent storage directories
RUN mkdir -p /app/voices /app/fertige_files

ENV VOICES_DIR=/app/voices \
    OUTPUT_DIR=/app/fertige_files \
    HOST=0.0.0.0 \
    PORT=8000 \
    PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

ENTRYPOINT ["uv", "run", "--no-dev", "pocket-tts"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000", "--voices-dir", "/app/voices"]
