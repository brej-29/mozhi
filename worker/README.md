# Mozhi search proxy (optional)

Without this, Mozhi answers open questions and "search" from Wikipedia (English, Tamil, Malayalam) and reads news through a free RSS-to-JSON service. Both need no key and work today. This Worker adds real web search and removes the third party from the news path, **without ever putting a key in the web page**.

| Safeguard | How |
|---|---|
| Key never reaches the browser | `TAVILY_API_KEY` is a Worker secret. The page only knows the Worker URL. |
| Stops at half the allowance | Every call is counted in KV before it is made. At `TAVILY_MONTHLY_LIMIT x CAP_FRACTION` (default 1,000 x 0.5 = 500 searches a month) `/search` returns 503 and the page falls back to Wikipedia. Check the limit on your Tavily dashboard and set `TAVILY_MONTHLY_LIMIT` to match. |
| One visitor cannot drain it | `PER_IP_DAILY` (default 15) searches a day per IP. |
| Browsers on other sites cannot call it | `ALLOWED_ORIGINS` (default `https://brej-29.github.io`). This is a CORS rule, not authentication: a script can fake the header, so rely on the caps. |
| Hard stop at the provider | In the Tavily dashboard set a usage limit on the account itself. KV counters are eventually consistent, so a burst can overshoot the half-way cap by a few calls; the account limit is the backstop. |
| No logging of queries | The Worker stores only counters. |

## Deploy (about five minutes, free plan)

You need a free Cloudflare account and a free Tavily key. I cannot do this step for you: it needs your logins.

```bash
cd worker
npx wrangler login
npx wrangler kv namespace create USAGE        # copy the id it prints into wrangler.toml
npx wrangler secret put TAVILY_API_KEY        # paste the key when asked; it is stored by Cloudflare, not in git
npx wrangler deploy                           # prints https://mozhi-proxy.<you>.workers.dev
```

Then set the printed URL in `mozhi/web/config.js`:

```js
window.MOZHI_PROXY = "https://mozhi-proxy.<you>.workers.dev";
```

Add the same origin to `connect-src` in the Content-Security-Policy of `mozhi/web/index.html`, commit, and the Pages workflow publishes it. The Worker URL is not a secret; the key is.

To turn search off at any time: `npx wrangler secret delete TAVILY_API_KEY`.
