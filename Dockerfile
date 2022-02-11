FROM python:3

WORKDIR /app

COPY ./app/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

ENTRYPOINT ["uvicorn", "--host", "0.0.0.0", "main:app", "--reload"]
