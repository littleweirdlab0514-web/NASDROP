# NASDrop 0.9.30-1 — X-Share recovery candidate

- Retries an interrupted X-Share one-time download three times with bounded 10, 20, and 30 second delays.
- Keeps the original job, destination, extraction options, and verified partial state when a fresh X-Share authorization is required.
- Adds a capability-gated endpoint that lets Chrome 0.5.12 or Android 0.8.22 attach a newly issued same-file URL to the waiting job.
- Keeps keyed URLs, provider cookies, request headers, and authentication material out of public job data and logs.

This is a Synology test candidate. Install it manually on DSM and use Chrome 0.5.12 or Android 0.8.22 to complete X-Share reauthentication after the server reports that three retries were exhausted.
