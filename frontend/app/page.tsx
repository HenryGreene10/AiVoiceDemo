export default function Page() {
  return (
    <>
      <header className="ea-nav">
        <div className="ea-nav-inner">
          <div className="ea-nav-left">
            <div className="ea-logo-mark">🎧</div>
            <div className="ea-logo-text">EasyAudio</div>
          </div>
          <nav className="ea-nav-links">
            <a href="#demo" className="ea-nav-link">
              Demo
            </a>
            <a href="#install" className="ea-nav-link">
              Install
            </a>
            <a href="#pricing" className="ea-nav-link ea-nav-link--dark">
              Pricing
            </a>
          </nav>
        </div>
      </header>

      <main className="ea-shell">
        {/* HERO */}
        <section className="ea-hero">
          <div className="ea-hero-card">
            <div className="ea-hero-corners">
              <div className="ea-corner ea-corner--tl" />
              <div className="ea-corner ea-corner--tr" />
              <div className="ea-corner ea-corner--bl" />
              <div className="ea-corner ea-corner--br" />
            </div>

            <div className="ea-badge">NEW • MICRO SAAS DEMO</div>

            <h1 className="ea-hero-title">
              Turn Any Article
              <br />
              Into Clean Audio
            </h1>

            <p className="ea-hero-subtitle">
              EasyAudio adds a tiny floating player to your articles. One script tag, natural voice,
              and server-side caching that keeps your TTS costs under control.
            </p>

            <div className="ea-hero-cta-row">
              <a href="#demo" className="ea-btn">
                ▶ Try the Live Demo
              </a>
              <a href="#pricing" className="ea-btn ea-btn--dark">
                View Pricing
              </a>
            </div>

            <div className="ea-hero-note">
              Scroll down to see the demo article, then keep scrolling for pricing &amp; install.
            </div>
          </div>
        </section>

        {/* DEMO SECTION */}
        <section id="demo" className="ea-section">
          <div className="ea-section-header">
            <h2 className="ea-section-title">Live Demo Article</h2>
            <p className="ea-section-subtitle">
              This is the kind of page your readers would see. The EasyAudio widget will inject a
              floating “Listen” button and mini-player on top of this content.
            </p>
          </div>

          <div className="ea-demo-article-wrap">
            <article className="ea-demo-article" id="ea-demo-article" data-ail-article>
              <h2>Why EasyAudio Makes Your Content Easier to Finish</h2>
              <p>
                Most readers love your ideas, but real life gets in the way — notifications,
                meetings, and ten open tabs. Audio gives them another path to finish what they
                started.
              </p>
              <p>
                EasyAudio turns this article into a clean, natural reading experience powered by AI.
                Instead of copying text into another app, your visitors tap play and keep listening
                while they switch tabs or put their phone in their pocket.
              </p>
              <p>
                The magic is that EasyAudio runs on your own backend. We request audio once, cache
                it on disk, and every future listen is instant. That means lower TTS costs and a
                faster experience for your readers.
              </p>
              <p>
                Below this paragraph, the page is just normal HTML — headings, paragraphs, links.
                The widget script finds the article content and wires up the mini-player
                automatically.
              </p>
              <p>
                Scroll a little further down for pricing ideas and an example install snippet you
                could drop into any blog or CMS template.
              </p>
            </article>
          </div>
        </section>

        {/* INSTALL */}
        <section id="install" className="ea-section">
          <div className="ea-section-header">
            <h2 className="ea-section-title">Install in One Script Tag</h2>
            <p className="ea-section-subtitle">
              Drop this at the bottom of your article template. The floating player does the rest.
            </p>
          </div>

          <div className="ea-install-card">
            <p
              style={{
                fontSize: 13,
                fontWeight: 700,
                marginTop: 0,
                marginBottom: 8,
              }}
            >
              Example snippet:
            </p>
            <pre
              style={{
                overflowX: "auto",
                padding: "10px 12px",
                background: "#212529",
                color: "#f8f9fa",
                border: "3px solid #212529",
                fontSize: 12,
                lineHeight: 1.5,
                boxShadow: "3px 3px 0 #495057",
              }}
            >{`<script
  src="https://hgtts.onrender.com/static/tts-widget.v1.js"
  data-ail-api-base="https://hgtts.onrender.com"
  data-ail-tenant="YOUR_TENANT_ID"
  defer
></script>`}</pre>
            <p
              style={{
                fontSize: 13,
                fontWeight: 700,
                color: "#495057",
                marginTop: 10,
              }}
            >
              Each customer would use their own <code>data-ail-tenant</code> so caching and billing
              stay tidy per site.
            </p>
          </div>
        </section>

        {/* PRICING */}
        <section id="pricing" className="ea-section">
          <div className="ea-section-header">
            <h2 className="ea-section-title">Simple Pricing for a Simple Player</h2>
            <p className="ea-section-subtitle">
              These are example plans for EasyAudio. Adjust limits later based on your traffic and
              TTS costs.
            </p>
          </div>

          <div className="ea-pricing-row">
            <div className="ea-plan">
              <div className="ea-plan-name">Starter</div>
              <div className="ea-plan-desc">For personal blogs &amp; small newsletters.</div>
              <div className="ea-plan-price">
                <span className="ea-plan-price-amount">$9</span>/month
              </div>
              <a href="#install" className="ea-plan-cta">
                Get Early Access
              </a>
              <ul className="ea-plan-features">
                <li>Up to 100 article renders / month</li>
                <li>EasyAudio mini-player on one site</li>
                <li>Server-side caching included</li>
                <li>Email support</li>
              </ul>
            </div>

            <div className="ea-plan ea-plan--highlight">
              <div className="ea-plan-label">Most Popular</div>
              <div className="ea-plan-name">Publisher</div>
              <div className="ea-plan-desc">For growing Substacks &amp; content sites.</div>
              <div className="ea-plan-price">
                <span className="ea-plan-price-amount">$29</span>/month
              </div>
              <a href="#install" className="ea-plan-cta">
                Get Early Access
              </a>
              <ul className="ea-plan-features">
                <li>Up to 500 article renders / month</li>
                <li>Mini-player on up to 3 sites</li>
                <li>Priority support</li>
                <li>Basic listener metrics</li>
              </ul>
            </div>

            <div className="ea-plan">
              <div className="ea-plan-name">Newsroom</div>
              <div className="ea-plan-desc">For high-volume blogs &amp; local media.</div>
              <div className="ea-plan-price">
                <span className="ea-plan-price-amount">$99</span>/month
              </div>
              <a href="#install" className="ea-plan-cta">
                Talk to Us
              </a>
              <ul className="ea-plan-features">
                <li>Custom article limits</li>
                <li>Multiple properties / sections</li>
                <li>Slack/email support</li>
                <li>Custom caching &amp; analytics options</li>
              </ul>
            </div>
          </div>
        </section>

      </main>

      <footer className="ea-footer">
        EasyAudio demo · Built to show how a tiny AI audio widget could feel in production.
        <small>Backend: Python + ElevenLabs · Frontend: Next.js + one script tag.</small>
      </footer>
    </>
  )
}
