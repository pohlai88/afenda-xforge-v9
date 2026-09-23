# syntax=docker/dockerfile:1
#
# AFENDA xForge image, built from this source tree.
#
# Build from the repository root (compose does this for you):
#   docker compose -f deploy/compose.yaml build
#
# Python 3.11 on purpose: it is the interpreter the test suite runs on
# (.venv/pyvenv.cfg), so the requirements.txt pins resolved here are the ones
# that were tested. On 3.12 reportlab 4.1 needs rl-renderPM, which
# requirements.txt only installs on win32.

ARG PYTHON_IMAGE=python:3.11-slim-bookworm

# --------------------------------------------------------------------------
# build: compile the Python dependencies into /opt/venv, fetch wkhtmltopdf
# --------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS build

ARG TARGETARCH
# wkhtmltopdf 0.12.6.1-3 (patched Qt) from the wkhtmltopdf project's own
# GitHub releases. Hashes computed once from the release assets and pinned;
# `sha256sum -c` fails the build if the download ever differs.
ARG WKHTMLTOX_VERSION=0.12.6.1-3
ARG WKHTMLTOX_SHA256_AMD64=98ba0d157b50d36f23bd0dedf4c0aa28c7b0c50fcdcdc54aa5b6bbba81a3941d
ARG WKHTMLTOX_SHA256_ARM64=b6606157b27c13e044d0abbe670301f88de4e1782afca4f9c06a5817f3e03a9c

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        build-essential libpq-dev libldap2-dev libsasl2-dev curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN case "${TARGETARCH}" in \
        amd64) sha="${WKHTMLTOX_SHA256_AMD64}" ;; \
        arm64) sha="${WKHTMLTOX_SHA256_ARM64}" ;; \
        *) echo "unsupported TARGETARCH '${TARGETARCH}' (amd64 and arm64 only)" >&2; exit 1 ;; \
    esac \
 && curl -fsSL -o /tmp/wkhtmltox.deb \
        "https://github.com/wkhtmltopdf/packaging/releases/download/${WKHTMLTOX_VERSION}/wkhtmltox_${WKHTMLTOX_VERSION}.bookworm_${TARGETARCH}.deb" \
 && echo "${sha}  /tmp/wkhtmltox.deb" | sha256sum -c -

RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# --------------------------------------------------------------------------
# runtime
# --------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS runtime

ENV PYTHONUNBUFFERED=1 \
    LANG=C.UTF-8

WORKDIR /tmp
COPY --from=build /tmp/wkhtmltox.deb ./wkhtmltox.deb
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        libpq5 libldap-2.5-0 libsasl2-2 libmagic1 \
        fontconfig fonts-noto-core fonts-noto-cjk gsfonts ca-certificates \
        ./wkhtmltox.deb \
 && rm -f ./wkhtmltox.deb \
 && rm -rf /var/lib/apt/lists/* \
 && fc-cache -f

RUN useradd --create-home --home-dir /home/afenda --shell /bin/sh afenda \
 && mkdir -p /var/lib/afenda /etc/afenda \
 && chown afenda:afenda /var/lib/afenda /etc/afenda \
 && install -d -m 755 /usr/local/lib/afenda
# ^ Created here because `COPY --chmod=644` into a missing directory gives
#   the directory 644 too, which the afenda user cannot traverse.

COPY --from=build /opt/venv /opt/venv

COPY --chmod=755 odoo-bin /opt/afenda/odoo-bin
COPY odoo /opt/afenda/odoo
COPY addons /opt/afenda/addons
COPY afenda/addons /opt/afenda/afenda/addons
COPY afenda/oca /opt/afenda/afenda/oca

COPY --chmod=755 deploy/entrypoint.sh /usr/local/bin/afenda-entrypoint
COPY --chmod=755 deploy/init.sh /usr/local/bin/afenda-init
COPY --chmod=644 deploy/init_params.py /usr/local/lib/afenda/init_params.py

ENV PATH=/opt/venv/bin:$PATH
USER afenda
WORKDIR /opt/afenda
VOLUME ["/var/lib/afenda"]
EXPOSE 8069 8072

ENTRYPOINT ["/usr/local/bin/afenda-entrypoint"]
# Run odoo-bin through the venv interpreter directly, never a wrapper script:
# the gevent child is re-executed from sys.argv[0] (odoo/service/server.py,
# long_polling_spawn), so argv[0] must be odoo-bin itself.
CMD ["/opt/venv/bin/python", "/opt/afenda/odoo-bin"]
