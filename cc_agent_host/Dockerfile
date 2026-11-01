FROM ghcr.io/home-assistant/base:3.24

RUN apk add --no-cache bash git jq nginx py3-aiohttp py3-yaml python3 ripgrep su-exec tmux ttyd yamllint

# Unprivileged user for jobs; the HA configuration is mounted below /srv/ha (root only)
RUN adduser -D -H -h /data/agent/home -s /sbin/nologin -u 1000 cc_agent \
    && mkdir -p /srv/ha && chmod 700 /srv/ha \
    && ln -s /srv/ha/config /homeassistant

# Official Claude Code native build (musl), pinned and checksum-verified.
# Same binary the official installer would place; it is not modified.
ARG CLAUDE_CODE_VERSION=2.1.316
ARG SHA512_ARM64=3048ab67a3455b8190843c07651dc4b9610843bdc08929abf959016e8862c193975ba15a27b4d0278ca937709d743067f0728f5d58298d84ac5247db2a8d4d49
ARG SHA512_X64=7e327ec4ce1c496f66feae998755bdb64ab421ae38184521d5319c26d72b3f014245678c08096e39fdacb79d4171a7adecc023067f52c2f2adb3deb08638505c
SHELL ["/bin/ash", "-eo", "pipefail", "-c"]
RUN case "$(apk --print-arch)" in \
        aarch64) pkg=linux-arm64-musl; sum="$SHA512_ARM64" ;; \
        x86_64)  pkg=linux-x64-musl;   sum="$SHA512_X64" ;; \
        *) echo "unsupported architecture" >&2; exit 1 ;; \
    esac \
    && curl -fsSL -o /tmp/cc.tgz \
        "https://registry.npmjs.org/@anthropic-ai/claude-code-${pkg}/-/claude-code-${pkg}-${CLAUDE_CODE_VERSION}.tgz" \
    && echo "${sum}  /tmp/cc.tgz" | sha512sum -c - \
    && tar -xzf /tmp/cc.tgz -C /tmp package/claude \
    && install -D -m 0755 /tmp/package/claude /usr/lib/cc_agent_host/claude \
    && rm -rf /tmp/cc.tgz /tmp/package \
    && /usr/lib/cc_agent_host/claude --version

ARG BUILD_VERSION=dev
# USE_BUILTIN_RIPGREP=0: Claude Code on musl uses the system ripgrep (official setup for Alpine)
ENV CC_VERSION=$BUILD_VERSION \
    HOME=/data/home \
    CLAUDE_CONFIG_DIR=/data/claude \
    DISABLE_AUTOUPDATER=1 \
    USE_BUILTIN_RIPGREP=0 \
    YAMLLINT_CONFIG_FILE=/usr/share/cc_agent_host/session/yamllint.yaml \
    LANG=C.UTF-8

COPY rootfs /

# `claude` on PATH: the launcher picks the version installed through the update entity, else the image's
RUN ln -s /usr/lib/cc_agent_host/cli-launcher /usr/local/bin/claude && claude --version
