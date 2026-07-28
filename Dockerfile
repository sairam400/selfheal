# Deploys the selfheal web demo (app.py) to Hugging Face Spaces via the
# Docker SDK, or anywhere else that runs a Dockerfile. Set ANTHROPIC_API_KEY
# as a secret in the hosting environment -- it is never baked into the image.
FROM python:3.11-slim

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -e ".[web]"

ENV HOST=0.0.0.0
ENV PORT=7860
EXPOSE 7860

CMD ["python", "app.py"]
