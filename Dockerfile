FROM python:3.12-slim
WORKDIR /app
COPY app.py game.py index.html app.js style.css ./
ENV HOST=0.0.0.0 PORT=8080 DATA_PATH=/data/game.sqlite PYTHONDONTWRITEBYTECODE=1
RUN mkdir /data && chown 1000:1000 /data
USER 1000:1000
EXPOSE 8080
CMD ["python", "app.py"]
