FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN RUN pip install -U yt-dlp
COPY . .
CMD ["python", "bot.py"]
