# -----------------------------------------------------------------------------
# Dockerfile for Rhasspy Raven Service
# (https://github.com/rhasspy/rhasspy-wake-raven-hermes)
#
# Requires Docker buildx: https://docs.docker.com/buildx/working-with-buildx/
# See scripts/build-docker.sh
#
# Builds a multi-arch image for amd64/armv6/armv7/arm64.
# The virtual environment from the build stage is copied over to the run stage.
# The Rhasspy source code is then copied into the run stage and executed within
# that virtual environment.
#
# Build stages are named build-$TARGETARCH$TARGETVARIANT, so build-amd64,
# build-armv6, etc. Run stages are named similarly.
#
# armv6 images (Raspberry Pi 0/1) are derived from balena base images:
# https://www.balena.io/docs/reference/base-images/base-images/#balena-base-images
#
# The IFDEF statements are handled by docker/preprocess.sh. These are just
# comments that are uncommented if the environment variable after the IFDEF is
# not empty.
#
# The build-docker.sh script will optionally add apt/pypi proxies running locally:
# * apt - https://docs.docker.com/engine/examples/apt-cacher-ng/ 
# * pypi - https://github.com/jayfk/docker-pypi-cache
# -----------------------------------------------------------------------------

FROM ubuntu:eoan as build-ubuntu

ENV LANG C.UTF-8

# IFDEF PROXY
#! RUN echo 'Acquire::http { Proxy "http://${PROXY}"; };' >> /etc/apt/apt.conf.d/01proxy
# ENDIF

RUN apt-get update && \
    apt-get install --no-install-recommends --yes \
        python3 python3-dev python3-setuptools python3-pip python3-venv \
        build-essential gfortran libopenblas-dev liblapack-dev cython libatlas-base-dev \
        curl ca-certificates

FROM build-ubuntu as build-amd64

FROM build-ubuntu as build-armv7

FROM build-ubuntu as build-arm64

# -----------------------------------------------------------------------------

FROM balenalib/raspberry-pi-debian-python:3.7-buster-build-20200604 as build-armv6

ENV LANG C.UTF-8

# IFDEF PROXY
#! RUN echo 'Acquire::http { Proxy "http://${PROXY}"; };' >> /etc/apt/apt.conf.d/01proxy
# ENDIF

RUN install_packages \
        gfortran libopenblas-dev liblapack-dev cython libatlas-base-dev \
        curl ca-certificates

# -----------------------------------------------------------------------------
# Build
# -----------------------------------------------------------------------------

ARG TARGETARCH
ARG TARGETVARIANT
FROM build-$TARGETARCH$TARGETVARIANT as build

ENV APP_DIR=/usr/lib/rhasspy-wake-raven-hermes
ENV BUILD_DIR=/build

# Directory of prebuilt tools
COPY download/ ${APP_DIR}/download/

COPY Makefile setup.py requirements.txt \
     ${APP_DIR}/

COPY scripts/ \
     ${APP_DIR}/scripts/

# IFDEF PYPI
#! ENV PIP_INDEX_URL=http://${PYPI}/simple/
#! ENV PIP_TRUSTED_HOST=${PYPI_HOST}
# ENDIF

RUN cd ${APP_DIR} && \
    make && \
    make install

# -----------------------------------------------------------------------------

FROM ubuntu:eoan as run-ubuntu

ENV LANG C.UTF-8

RUN apt-get update && \
    apt-get install --yes --no-install-recommends \
        python3 libpython3.7 \
        liblapack3 libatlas-base-dev \
        sox

FROM run-ubuntu as run-amd64

FROM run-ubuntu as run-armv7

FROM run-ubuntu as run-arm64

# -----------------------------------------------------------------------------

FROM balenalib/raspberry-pi-debian-python:3.7-buster-run-20200604 as run-armv6

ENV LANG C.UTF-8

RUN install_packages \
        python3 libpython3.7 \
        liblapack3 libatlas-base-dev \
        sox 

# -----------------------------------------------------------------------------
# Run
# -----------------------------------------------------------------------------

ARG TARGETARCH
ARG TARGETVARIANT
FROM run-$TARGETARCH$TARGETVARIANT

ENV APP_DIR=/usr/lib/rhasspy-wake-raven-hermes
COPY --from=build ${APP_DIR}/.venv/ ${APP_DIR}/.venv/

# Copy source
COPY rhasspywake_raven_hermes/ ${APP_DIR}/rhasspywake_raven_hermes/
COPY bin/rhasspy-wake-raven-hermes ${APP_DIR}/bin/

ENTRYPOINT ["bash", "/usr/lib/rhasspy-wake-raven-hermes/bin/rhasspy-wake-raven-hermes"]
