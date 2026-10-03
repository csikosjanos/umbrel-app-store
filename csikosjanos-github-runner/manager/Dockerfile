# Runner manager: the myoung34 runner image (same job toolchain as app 1.x)
# plus a small Python supervisor + web UI that runs N runners in one container.
# Built by .github/workflows/build-github-runner-manager.yml.
FROM myoung34/github-runner:2.337.0-ubuntu-noble

COPY manager.py index.html /opt/manager/

EXPOSE 8080
# dumb-init (in the base image) forwards SIGTERM so runners stop gracefully.
ENTRYPOINT ["/usr/bin/dumb-init", "--"]
CMD ["python3", "/opt/manager/manager.py"]
