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

              <div data-ail-body>
                <p>
                  Most blogs have dozens, hundreds, or even thousands of articles. They could
                  regenerate audio files, upload MP3s, place audio blocks manually, and redo
                  everything when an article changes. But why would they?
                </p>
                <p>
                  EasyAudio gives them the hands-free version. With a single script added to your
                  article template, every post on your site becomes playable. A Listen button appears
                  under the title, we extract the text, generate the narration, and cache it. If you
                  update the article, the audio updates automatically and your readers just hit play.
                </p>
                <p>
                  There are no extra steps in your publishing flow, no exporting or uploading audio
                  files, and no one on your team needs to learn ElevenLabs. It simply runs in the
                  background and keeps your articles listenable at scale.
                </p>
              </div>
            </article>
          </div>
        </section>

        <section className="ea-section">
          <div className="ea-section-header">
            <h2 className="ea-section-title">Why Publishers Use EasyAudio</h2>
            <p className="ea-section-subtitle">
              Readers don&apos;t pay for raw TTS. They pay for automation, embedding, branding, and a
              listening experience that requires zero maintenance from the newsroom.
            </p>
          </div>
          <ul className="ea-plan-features">
            <li>A Listen button on every article with one script</li>
            <li>Automatic text extraction, narration, and caching</li>
            <li>Pay once per article playback thanks to caching</li>
            <li>Works on mobile and desktop — no extensions or installs</li>
            <li>Inline player that matches your brand</li>
            <li>Zero maintenance for your team</li>
          </ul>
        </section>

        {/* INSTALL */}
        <section id="install" className="ea-section">
          <div className="ea-section-header">
            <h2 className="ea-section-title">Install in 30 Seconds</h2>
            <p className="ea-section-subtitle">
              EasyAudio installs with a single HTML snippet added to your article template. Prefer
              someone else to wire it up? We&apos;ll set it up for you for free.
            </p>
          </div>

          <div className="ea-install-card">
            <a
              className="ea-plan-cta"
              href="mailto:hello@easyaudio.dev?subject=EasyAudio%20Setup"
            >
              Get Free Installation
            </a>
            <details style={{ marginTop: 16 }}>
              <summary style={{ cursor: "pointer", fontWeight: 600 }}>Developer snippet</summary>
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
                  marginTop: 12,
                }}
              >{`<script
  src="https://YOUR_RENDER_DOMAIN/static/tts-widget.v1.js"
  data-ail-api-base="https://YOUR_RENDER_DOMAIN"
  data-ail-tenant="demo"
  defer
></script>
<button data-ail-listen>Listen</button>`}</pre>
            </details>
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
