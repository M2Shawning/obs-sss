FROM python:3

WORKDIR /app

COPY ./app/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

ENTRYPOINT [ "tail" ]
CMD [ "-f", "/dev/null" ]
