FROM python:3

COPY entrypoint.sh requirements.txt /

RUN pip install -r requirements.txt ptr

ENTRYPOINT ["/entrypoint.sh"]
