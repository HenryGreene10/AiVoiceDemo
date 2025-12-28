import Script from "next/script"

export default function Page() {
  return (
    <>
      <Script id="ms-clarity" strategy="afterInteractive">
        {`(function(c,l,a,r,i,t,y){
        c[a]=c[a]||function(){(c[a].q=c[a].q||[]).push(arguments)};
        t=l.createElement(r);t.async=1;t.src="https://www.clarity.ms/tag/"+i;
        y=l.getElementsByTagName(r)[0];y.parentNode.insertBefore(t,y);
    })(window, document, "clarity", "script", "un0i0tws0o");`}
      </Script>
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
            <h1 className="ea-hero-title">Turn Any Article Into an Elevated Listening Experience</h1>
            <div className="ea-hero-cta-row">
              <a href="#install" className="ea-plan-cta ea-hero-cta">
                Install with Ghost
              </a>
            </div>
          </div>
        </section>

        {/* DEMO SECTION */}
        <section id="demo" className="ea-section ea-demo-section">
          <article className="ea-demo-article" data-ail-article>
            <h1 className="ea-demo-title" data-ail-title>
              How EasyAudio Makes Your Work More Impactful
            </h1>
            <p className="ea-demo-author" data-ail-author>
              By Henry Greene
            </p>
            <div className="ea-demo-listen-row">
              <button
                type="button"
                id="ail-listen-btn"
                className="ea-listen-button ea-demo-listen-btn listen-btn ail-listen"
                data-ail-listen="true"
              >
                Listen
              </button>
            </div>

            <div className="ea-demo-body" data-ail-body>
              <p>
                Some readers love audio versions of articles. They can listen on the go, or follow along as they read. According to a study done at Carnegie Mellon University, brain scans show that reading and listening activate 
                overlapping language processing areas in the brain, causing a stronger memory trace. With audio available, your viewers will spend more time on your site, stay engaged longer, and share your content more frequently.  
              </p>
              <p>
                EasyAudio makes it effortless to add clean and natural voiceovers to your page. Add a single script to your site and your articles instantly becomes playable. 
                A “Listen” button appears under the title, as shown in the demo, and plays narration through the built-in mini-player. If you update your text, the audio will update automatically!
              </p>
              <p>
                There are no extra steps in your publishing workflow. No exporting. No uploading. 
                Everything runs quietly in the background and makes your articles listenable at unlimited scale.
              </p>
            </div>
          </article>
        </section>

        {/* PRICING */}
        <section id="pricing" className="ea-section">
          <div className="ea-pricing-shell">
            <div className="ea-section-header">
              <h2 className="ea-section-title">Simple Pricing for a Simple Player</h2>
              <p className="ea-section-subtitle">
                Every plan includes a 7-day free trial. Try EasyAudio on your site, cancel anytime.
              </p>
            </div>

            <div className="ea-plan-row">
              <div className="ea-plan ea-plan--highlight">
                <div className="ea-plan-name ea-pricing-plan-title">Starter</div>
                <div className="ea-plan-desc">For personal blogs &amp; small newsletters.</div>
                <div className="ea-plan-price ea-pricing-price">
                  <span className="ea-plan-price-amount">$9</span>/month
                </div>
                <a
                  href="https://buy.stripe.com/fZu7sLgjy83M4B15dbcQU02"
                  className="ea-plan-cta"
                  target="_blank"
                  rel="noreferrer"
                >
                  Start free trial
                </a>
                <ul className="ea-plan-features">
                  <li>For authors, bloggers, and small sites</li>
                  <li>Up to 2 hours of <i>unique</i> audio renders per month</li>
                  <li>Unlimited playback</li>
                  <li>Complimentary installation and 24/7 email support</li>
                </ul>
              </div>

              <div className="ea-plan ea-plan--highlight">
                <div className="ea-plan-name ea-pricing-plan-title">Publisher</div>
                <div className="ea-plan-desc">For growing Substacks &amp; content sites.</div>
                <div className="ea-plan-price ea-pricing-price">
                  <span className="ea-plan-price-amount">$29</span>/month
                </div>
                <a
                  href="https://buy.stripe.com/00w6oH1oE4RA6J95dbcQU01"
                  className="ea-plan-cta"
                  target="_blank"
                  rel="noreferrer"
                >
                  Start free trial
                </a>
                <ul className="ea-plan-features">
                  <li>For larger content teams</li>
                  <li>Up to 10 hours of <i>unique</i> audio renders per month</li>
                  <li>Unlimited playback and customizable voices</li>
                  <li>Complimentary installation and 24/7 email support</li>
                </ul>
              </div>

              <div className="ea-plan ea-plan--highlight">
                <div className="ea-plan-name ea-pricing-plan-title">Newsroom</div>
                <div className="ea-plan-desc">For professional publishers and newsrooms.</div>
                <div className="ea-plan-price ea-pricing-price">
                  <span className="ea-plan-price-amount">$99</span>/month
                </div>
                <a
                  href="https://buy.stripe.com/8x2aEX8R6bfY0kL9trcQU00"
                  className="ea-plan-cta"
                  target="_blank"
                  rel="noreferrer"
                >
                  Start free trial
                </a>
                <ul className="ea-plan-features">
                  <li>For professional publishers</li>
                  <li>Up to 50 hours of <i>unique</i> audio renders per month</li>
                  <li>Unlimited playback and customizable voices</li>
                  <li>Complimentary installation and priority support</li>
                </ul>
              </div>
            </div>
          </div>
        </section>

        {/* INSTALL */}
        <section id="install" className="ea-section ea-install-section">
          <div className="ea-section-header">
            <h2 className="ea-section-title">Install with Ghost</h2>
            <p className="ea-section-subtitle">
              Add EasyAudio to Ghost in minutes with a simple copy-paste.
            </p>
          </div>

          <div className="ea-install-card">
            <ol className="ea-install-steps">
              <li>
                <strong>Checkout and get your snippet.</strong> We email your EasyAudio key right away.
              </li>
              <li>
                <strong>Paste it into Ghost.</strong> In Ghost Admin, go to Settings &gt; Code Injection
                and paste the snippet.
              </li>
              <li>
                <strong>Publish and listen.</strong> Refresh any post and the Listen button appears
                automatically.
              </li>
            </ol>
            <div className="ea-install-media">
              <div className="ea-install-shot">
                <div className="ea-install-shot-label">1 Open Code Injection</div>
                <div className="ea-install-shot-frame">
                  <img
                    src="/install/ghost-step-1-code-injection.png"
                    alt="Ghost Admin code injection screen"
                  />
                </div>
              </div>
              <div className="ea-install-shot">
                <div className="ea-install-shot-label">2 Paste the snippet</div>
                <div className="ea-install-shot-frame">
                  <img
                    src="/install/ghost-step-2-paste-snippet.png"
                    alt="Paste the EasyAudio snippet in Ghost"
                  />
                </div>
              </div>
              <div className="ea-install-shot">
                <div className="ea-install-shot-label">3 Save and test</div>
                <div className="ea-install-shot-frame">
                  <img
                    src="/install/ghost-step-3-listen-button.png"
                    alt="Listen button visible on a Ghost post"
                  />
                </div>
              </div>
            </div>
            <a href="#pricing" className="ea-plan-cta ea-install-cta">
              Install with Ghost
            </a>
            <p className="ea-install-note">
              <strong>Other platforms:</strong> WordPress, Webflow, and custom sites use a similar
              one-snippet install. If you need help, we&apos;ll guide you.
            </p>
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
        </div>
      </main>

      <footer className="ea-footer">
        <small>© {new Date().getFullYear()} EasyAudio.</small>
      </footer>
    </>
  )
}
