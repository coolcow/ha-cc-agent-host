FROM ghcr.io/home-assistant/base:3.24

RUN apk add --no-cache bash git jq nginx py3-aiohttp py3-yaml python3 ripgrep su-exec tmux ttyd yamllint

# Unprivileged user for jobs; the HA configuration is mounted below /srv/ha (root only)
RUN adduser -D -H -h /data/agent/home -s /sbin/nologin -u 1000 cc_agent \
    && mkdir -p /srv/ha && chmod 700 /srv/ha \
    && ln -s /srv/ha/config /homeassistant

# Official Claude Code native build (musl), pinned and checksum-verified.
# Same binary the official installer would place; it is not modified.
ARG CLAUDE_CODE_VERSION=2.1.291
ARG SHA512_ARM64=f6567d64497199d46a5747a58626ca6d7c28247af2e704467e5b1d29fecb855a292994ffc2c1aa20582dea6c3c3590d0fc11945f916017d627eb4759e643ad15
ARG SHA512_X64=728193aea1249422c179dfa2d855f383fdc8a8720f77dfe61938a712a3bc22598a93ca8ea856137f9cd0cc9f66dff4fea7d42dda6d77d78fd2d3480e53f15e9b
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
