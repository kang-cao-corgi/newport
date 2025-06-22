FROM python:3.11

RUN pip install uv

WORKDIR /app
COPY . .

RUN uv sync

ENTRYPOINT ["uv", "run", "python"]
CMD ["main.py"]
