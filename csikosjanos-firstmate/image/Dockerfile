# firstmate for Umbrel: one image, two services (see ../docker-compose.yml).
#   fm  (default CMD)  tmux in the browser via ttyd, harnesses, gh, git
#   web (python3 /opt/firstmate-web/server.py)  settings UI + terminal proxy
# Built by .github/workflows/build-firstmate.yml (amd64 only). Every upstream
# is pinned: base image by digest, binaries by version + sha256, npm packages
# by exact version, firstmate by commit (cloned at first start, not baked in).
FROM node:22.23.3-bookworm-slim@sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c

ARG TTYD_VERSION=1.7.7
ARG TTYD_SHA256=8a217c968aba172e0dbf3f34447218dc015bc4d5e59bf51db2f2cd12b7be4f55
ARG GH_VERSION=2.102.0
ARG GH_SHA256=bb766f710eef8ede859c18578c72c327597cd4c8a85b06001b1f3843c6019386
ARG CLAUDE_CODE_VERSION=2.1.289
ARG OPENCODE_VERSION=1.18.34
ARG PI_VERSION=1.0.3

# firstmate's own helpers need bash, jq, python3, perl, curl, lsof, pgrep,
# openssl, sha256sum; the rest is a reasonable dev toolbox for the crew.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      bash-completion build-essential ca-certificates curl file git jq less lsof nano \
      ncurses-term openssh-client openssl perl procps python3 python3-pip python3-venv \
      ripgrep tini tmux unzip vim-tiny xz-utils zip \
 && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL -o /usr/local/bin/ttyd \
      "https://github.com/tsl0922/ttyd/releases/download/${TTYD_VERSION}/ttyd.x86_64" \
 && echo "${TTYD_SHA256}  /usr/local/bin/ttyd" | sha256sum -c - \
 && chmod 755 /usr/local/bin/ttyd \
 && curl -fsSL -o /tmp/gh.tgz \
      "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_amd64.tar.gz" \
 && echo "${GH_SHA256}  /tmp/gh.tgz" | sha256sum -c - \
 && tar -xzf /tmp/gh.tgz -C /tmp \
 && install -m 755 "/tmp/gh_${GH_VERSION}_linux_amd64/bin/gh" /usr/local/bin/gh \
 && rm -rf /tmp/gh.tgz "/tmp/gh_${GH_VERSION}_linux_amd64"

# Harnesses, into the image's /usr/local. Upgrades done later with
# `npm i -g ...` land in /root/.npm-global (persistent, first on PATH).
RUN npm install -g --prefix /usr/local \
      "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" \
      "opencode-ai@${OPENCODE_VERSION}" \
      "@earendil-works/pi-coding-agent@${PI_VERSION}" \
 && npm cache clean --force \
 && rm -rf /root/.npm /root/.cache

# git over HTTPS to GitHub authenticates through gh (GH_TOKEN or gh auth login).
RUN git config --system credential.https://github.com.helper '' \
 && git config --system --add credential.https://github.com.helper '!/usr/local/bin/gh auth git-credential' \
 && git config --system credential.https://gist.github.com.helper '' \
 && git config --system --add credential.https://gist.github.com.helper '!/usr/local/bin/gh auth git-credential'

COPY rootfs/ /
COPY web/server.py web/index.html /opt/firstmate-web/
RUN chmod 755 /usr/local/bin/fm-start /usr/local/bin/fm-session \
 && echo '. /etc/firstmate/env-hook.sh' >> /etc/bash.bashrc

ENV LANG=C.UTF-8 \
    HOME=/root \
    BASH_ENV=/etc/firstmate/env-hook.sh \
    NPM_CONFIG_PREFIX=/root/.npm-global \
    PATH=/root/.local/bin:/root/.npm-global/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    FIRSTMATE_REPO=https://github.com/kunchenguid/firstmate \
    FIRSTMATE_REF=e5b9dddc982e546b81b4bfce754df1465270a59e \
    TTYD_SOCK=/run/fm/ttyd.sock

# Fail the build if a tool is missing or does not start (versions go to the build log).
RUN ttyd --version && tmux -V && gh --version | head -1 && git --version \
 && claude --version && opencode --version && pi --version

WORKDIR /root
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/usr/local/bin/fm-start"]
