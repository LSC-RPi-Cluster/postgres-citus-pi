FROM arm32v7/postgres:12.3-alpine
ARG VERSION=9.4.0
LABEL maintainer="lucas-fs - lferreira@inf.ufsm.br" \
      org.label-schema.name="Citus" \
      org.label-schema.description="Scalable PostgreSQL for multi-tenant and real-time workloads" \
      org.label-schema.url="https://www.citusdata.com" \
      org.label-schema.vcs-url="https://github.com/citusdata/citus" \
      org.label-schema.vendor="Citus Data, Inc." \
      org.label-schema.version=${VERSION}-alpine \
      org.label-schema.schema-version="1.0"

RUN apk add --no-cache \
            --virtual builddeps \
        build-base \
        curl \
        curl-dev \
        openssl-dev \
        ca-certificates \
        clang \
        llvm \
        icu-dev && \
    apk add --no-cache libcurl && \
    curl -sfLO "https://github.com/citusdata/citus/archive/v${VERSION}.tar.gz" && \
    tar xzf "v${VERSION}.tar.gz" && \
    cd "citus-${VERSION}" && \
    ./configure && \
    make install && \
    cd .. && \
    rm -rf "citus-${VERSION}" "v${VERSION}.tar.gz" && \
    apk del builddeps

# add citus to default PostgreSQL config
RUN echo "shared_preload_libraries='citus'" >> /usr/local/share/postgresql/postgresql.conf.sample

# add scripts to run after initdb
COPY 001-create-citus-extension.sql /docker-entrypoint-initdb.d/

# add boot check script
COPY boot-check.sh /
RUN chmod +x /boot-check.sh

# entry point unsets PGPASSWORD, but we need it to connect to workers
# https://github.com/docker-library/postgres/blob/33bccfcaddd0679f55ee1028c012d26cd196537d/12/docker-entrypoint.sh#L303
RUN sed "/unset PGPASSWORD/d" -i /usr/local/bin/docker-entrypoint.sh

CMD ["/bin/bash", "-c", "/boot-check.sh"]
