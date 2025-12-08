export default function Page() {
  return (
    <>
      <header className="ea-nav">
        <div className="ea-nav-inner">
          <span className="ea-nav-title">EasyAudio</span>
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
          <div className="ea-card ea-hero-card">
            <h1 className="ea-hero-title">Turn Any Article Into a Clean Listening Experience</h1>
          </div>
        </section>

        {/* DEMO SECTION */}
        <section id="demo" className="ea-section">
          <div className="ea-demo-article-wrap">
            <article className="ea-demo-article" id="ea-demo-article" data-ail-article>
              <header className="ea-article-header">
                <h1 data-ail-title>Why EasyAudio Makes Your Articles Easier to Finish</h1>
                <p className="ea-article-meta" data-ail-author>
                  By Henry Greene
                </p>
                <button
                  id="ail-listen-btn"
                  className="ea-listen-button listen-btn ail-listen"
                  data-ail-listen="true"
                  type="button"
                >
                  Listen
                </button>
              </header>

              <div data-ail-body>
                <h2>Give Every Article a Voice</h2>
                <p>
                  EasyAudio is a lightweight widget that adds a Listen button and a calm mini player
                  to every story you choose. It turns your writing into a clear, natural listening
                  experience so readers can stay with your work even when they can&apos;t sit and read.
                </p>

                <h2>Help Readers Stay Connected With Your Work</h2>
                <p>
                  EasyAudio gives your audience a high-quality audio version of your writing so they
                  can stay engaged in moments when reading is not convenient. A natural and expressive
                  voice helps your ideas land more clearly and encourages readers to finish more of
                  what you share.
                </p>
                <p>
                  It enhances the overall experience of your content and helps people stay connected
                  to your work in a way that feels simple and intuitive.
                </p>

                <h2>Audio for Any Article You Choose</h2>
                <p>
                  Whether you publish essays, newsletters, research notes or community updates,
                  EasyAudio adds a polished listening option right when the article goes live.
                  There is nothing extra for you to produce. You simply write, and your readers
                  can choose to listen.
                </p>
                <p>
                  Under the hood it is a small, lightweight widget. In practice it feels like an
                  extra path into your work: a natural voice, attached to any article you care about,
                  that quietly helps readers stay with you from start to finish.
                </p>
              </div>
            </article>
          </div>
        </section>

        {/* INSTALL */}
        <section id="install" className="ea-section">
          <div className="ea-section-header">
            <h2 className="ea-section-title">Install in One Script Tag</h2>
            <p className="ea-section-subtitle">
              Add EasyAudio to any article template with a simple three-line HTML embed.
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
                background: "#1a1c1a",
                color: "#f3dfc1",
                border: "2px solid #e0c9a6",
                fontSize: 12,
                lineHeight: 1.5,
                boxShadow: "0 8px 18px rgba(0,0,0,0.25)",
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
                color: "#4b3f2f",
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
          <div className="ea-pricing-shell">
            <div className="ea-section-header">
              <h2 className="ea-section-title">Simple Pricing for a Simple Player</h2>
              <p className="ea-section-subtitle">
                These are example plans for EasyAudio. Adjust limits later based on your traffic and
                TTS costs.
              </p>
            </div>

            <div className="ea-pricing-row">
              <div className="ea-plan">
                <div className="ea-plan-name ea-pricing-plan-title">Starter</div>
                <div className="ea-plan-desc">For personal blogs &amp; small newsletters.</div>
                <div className="ea-plan-price ea-pricing-price">
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
                <div className="ea-plan-name ea-pricing-plan-title">Publisher</div>
                <div className="ea-plan-desc">For growing Substacks &amp; content sites.</div>
                <div className="ea-plan-price ea-pricing-price">
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
                <div className="ea-plan-name ea-pricing-plan-title">Newsroom</div>
                <div className="ea-plan-desc">For high-volume blogs &amp; local media.</div>
                <div className="ea-plan-price ea-pricing-price">
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
          </div>
        </section>

      </main>

      <footer className="ea-footer">
        <small>© {new Date().getFullYear()} EasyAudio.</small>
      </footer>
    </>
  )
}
