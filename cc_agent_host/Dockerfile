FROM ghcr.io/home-assistant/base:3.24

RUN apk add --no-cache bash git jq nginx py3-aiohttp py3-yaml python3 su-exec tmux ttyd

# Unprivileged user for jobs; the HA configuration is mounted below /srv/ha (root only)
RUN adduser -D -H -h /data/agent/home -s /sbin/nologin -u 1000 cc_agent \
    && mkdir -p /srv/ha && chmod 700 /srv/ha \
    && ln -s /srv/ha/config /homeassistant

# Official Claude Code native build (musl), pinned and checksum-verified.
# Same binary the official installer would place; it is not modified.
ARG CLAUDE_CODE_VERSION=2.1.287
ARG SHA512_ARM64=b1d16faba01ab31bf507392a91454f67219a2b100b7539a8d01d372bbcec07b2edf110f33a7ff2423eaf3e5b92ff8eb85e42f2aa57ac4ecce262d91d3a98e873
ARG SHA512_X64=801393e04e9f45a109f8fc8ffca53ae9d227f9a5e867ffa332414b24535cb04a692061f547d9fdd2b57bfe51d9af8ddbff49e01cf7389fe251ad52b3fc05fafd
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
    && install -m 0755 /tmp/package/claude /usr/local/bin/claude \
    && rm -rf /tmp/cc.tgz /tmp/package \
    && claude --version

ARG BUILD_VERSION=dev
ENV CC_VERSION=$BUILD_VERSION \
    HOME=/data/home \
    CLAUDE_CONFIG_DIR=/data/claude \
    DISABLE_AUTOUPDATER=1 \
    LANG=C.UTF-8

COPY rootfs /
