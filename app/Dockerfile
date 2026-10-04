ARG BUILD_ARCH=amd64

# Build the Vue app in the Supervisor's local app/ context; Node stays out of runtime.
FROM node:22-alpine AS ui
WORKDIR /ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci
COPY ui/ ./
RUN npm run build

FROM ghcr.io/home-assistant/${BUILD_ARCH}-base-python:3.13-alpine3.22

RUN apk add --no-cache ffmpeg \
    && pip install --no-cache-dir \
        "fastapi==0.142.2" \
        "starlette==1.7.0" \
        "uvicorn[standard]==0.54.0" \
        "httpx==0.28.1" \
        "pydantic==2.12.2"

COPY src /opt/sound-effects-studio/src
COPY --from=ui /ui/dist /opt/sound-effects-studio/src/sound_effects_studio/static/ui
COPY rootfs /

ENV PYTHONPATH=/opt/sound-effects-studio/src
RUN chmod 0755 /usr/bin/sound-effects-studio

CMD ["/usr/bin/sound-effects-studio"]
