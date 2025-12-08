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
        <div className="ea-page-inner">
          {/* HERO */}
        <section className="ea-hero">
          <div className="ea-card ea-hero-card">
            <h1 className="ea-hero-title">Turn Any Article Into a High-Quality Listening Experience</h1>
          </div>
        </section>

        {/* DEMO SECTION */}
        <section id="demo" className="ea-section">
          <div className="ea-demo-article-wrap">
            <article className="ea-demo-article" id="ea-demo-article" data-ail-article>
              <h1 data-ail-title>Why EasyAudio Makes Your Articles More Impactful</h1>
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

                <div className="ea-article-body" data-ail-body>
                <p>
                  Readers love audio versions of articles. They spend more time on your site, remain engaged
                  longer, and share articles more frequently when they can listen instead while they read.
                </p>
                <p>
                  EasyAudio enables seemless integration of clean audio voiceovers. By adding a single script to your
                  article, the pieces on your site instantly become playable. A "Listen" button appears
                  under the title, generates the narration, and plays through the mini-player. If you
                  update the article, the audio updates automatically.
                </p>
                <p>
                  There are no extra steps in your publishing flow, no exporting or uploading audio
                  files. It simply runs in the background and keeps all of your articles listenable at scale.
                </p>
              </div>
            </article>
          </div>
        </section>

        {/* PRICING */}
        <section id="pricing" className="ea-section">
          <div className="ea-pricing-shell">
            <div className="ea-section-header">
              <h2 className="ea-section-title">Simple Pricing for a Simple Player</h2>
            </div>

            <div className="ea-plan-row">
              <div className="ea-plan">
                <div className="ea-plan-name ea-pricing-plan-title">Free Trial</div>
                <div className="ea-plan-desc">Try a week free!</div>
                <div className="ea-plan-price ea-pricing-price">
                  <span className="ea-plan-price-amount">$0</span>
                </div>
                <a href="#install" className="ea-plan-cta">
                  Get Access
                </a>
                <ul className="ea-plan-features">
                  <li>Up to 10 article renders</li>
                  <li>EasyAudio mini-player on one site</li>
                  <li>Server-side caching included</li>
                  <li>Email support</li>
                </ul>
              </div>

              <div className="ea-plan">
                <div className="ea-plan-name ea-pricing-plan-title">Starter</div>
                <div className="ea-plan-desc">For personal blogs &amp; small newsletters.</div>
                <div className="ea-plan-price ea-pricing-price">
                  <span className="ea-plan-price-amount">$9</span>/month
                </div>
                <a href="#install" className="ea-plan-cta">
                  Get Access
                </a>
                <ul className="ea-plan-features">
                  <li>Up to 100 article renders / month</li>
                  <li>EasyAudio mini-player on one site</li>
                  <li>Server-side caching included</li>
                  <li>Email support</li>
                </ul>
              </div>

              <div className="ea-plan ea-plan--highlight">
                <div className="ea-plan-name ea-pricing-plan-title">Publisher</div>
                <div className="ea-plan-desc">For growing Substacks &amp; content sites.</div>
                <div className="ea-plan-price ea-pricing-price">
                  <span className="ea-plan-price-amount">$29</span>/month
                </div>
                <a href="#install" className="ea-plan-cta">
                  Get Access
                </a>
                <ul className="ea-plan-features">
                  <li>Up to 500 article renders / month</li>
                  <li>Mini-player on up to 3 sites</li>
                  <li>Priority support</li>
                  <li>Basic listener metrics</li>
                </ul>
              </div>
            </div>
          </div>
        </section>

        <section className="ea-section">
          <div className="ea-section-header">
            <h2 className="ea-section-title">Why Publishers Use EasyAudio</h2>
          </div>
          <div className="ea-why-table">
            <div className="ea-why-card">
              <strong>A single script</strong>
              <p>One embed lights up a Listen button across every article template.</p>
            </div>
            <div className="ea-why-card">
              <strong>Automatic narration</strong>
              <p>We extract clean text, generate narration, and cache it for you.</p>
            </div>
            <div className="ea-why-card">
              <strong>Predictable costs</strong>
              <p>Pay once per new article render instead of every playback.</p>
            </div>
            <div className="ea-why-card">
              <strong>Works everywhere</strong>
              <p>Mobile, desktop, and tablet players load instantly with no extensions.</p>
            </div>
            <div className="ea-why-card">
              <strong>On-brand player</strong>
              <p>The inline mini-player adopts your fonts and palette automatically.</p>
            </div>
            <div className="ea-why-card">
              <strong>Zero maintenance</strong>
              <p>No file exporting or uploads. Update an article and the audio updates too.</p>
            </div>
          </div>
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
  src="https://hgtts.onrender.com/static/tts-widget.v1.js"
  data-ail-api-base="https://hgtts.onrender.com"
  data-ail-tenant="demo"
  defer
></script>
<button data-ail-listen>Listen</button>`}</pre>
            </details>
          </div>
        </section>
        </div>
      </main>

      <footer className="ea-footer">
        <small>© {new Date().getFullYear()} EasyAudio.</small>
      </footer>
    </>
  )
}
