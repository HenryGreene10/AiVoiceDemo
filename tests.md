Manual test plan

1) Token issue
- POST /sdk/token with body {"origin":"https://localhost","path":"/synthesize"}
- Expect { token, exp }

2) First synth
- POST /synthesize { text: "Hello world" } with Authorization: Bearer <token> and Origin: https://localhost
- Expect { audioUrl, cache:"miss" }

3) Cache hit
- Repeat request
- Expect { cache:"hit" }

4) Secrets reuse
- Redeploy or cold start; call synth again and confirm no Secrets Manager error

5) LRU reaper
- Upload >2.5GB into cache/ then call synth; verify cache size trimmed below MAX_CACHE_BYTES

6) Loader SPA
- Serve web/loader.js + web/player.js on a SPA site; navigate between two articles; player updates source and keeps working


