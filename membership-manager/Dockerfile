FROM python:3-alpine

RUN apk add --no-cache \
            --virtual psycodeps \
        gcc \
        musl-dev \
        postgresql-dev \
        postgresql-client \
        python3-dev && \
    pip install docker psycopg2 && \
    apk add --no-cache libpq && \
    apk del psycodeps

ADD manager.py /

# add boot check script
COPY boot-check.sh /
RUN chmod +x /boot-check.sh

# -u in python is necessary to flush logging to docker in a timely manner
CMD ["/bin/sh", "-c", "/boot-check.sh && python -u ./manager.py"]

