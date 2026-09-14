/** CTA and footer for the marketing site. */

function AgileLabsSection() {
  return (
    <section style={{ padding: '120px', background: '#061033', position: 'relative' }}>
      <div style={{ maxWidth: 920 }}>
        <h2 className="ad-h1">
          <span className="ad-red-dark" style={{ fontWeight: 700 }}>Agile </span>
          <span style={{ fontWeight: 500 }}>Labs</span>
        </h2>
        <p className="ad-body" style={{ maxWidth: 680, marginTop: 24 }}>
          Specialized staff and facilities that stretch the limits of
          innovation, utilizing the latest technologies and innovative
          solutions to revolutionize customer missions.
        </p>
        <a className="ad-btn ad-btn--primary" style={{ marginTop: 40 }}>
          <svg viewBox="0 0 16 16" fill="none"><path d="M3 8h10M9 4l4 4-4 4" stroke="white" strokeWidth="1.5"/></svg>
          LEARN MORE
        </a>
      </div>
    </section>
  );
}

function FinalCTA() {
  return (
    <section style={{ padding: '120px', background: '#061033' }}>
      <div style={{ maxWidth: 1157 }}>
        <h2 className="ad-h1" style={{ fontSize: 96, fontWeight: 500, lineHeight: 1.05 }}>
          <span style={{ fontWeight: 700 }}>Advancing </span>
          <span>Together</span>
        </h2>
        <p className="ad-body" style={{ maxWidth: 540, marginTop: 32 }}>
          We listen carefully and collaborate closely to understand your
          challenges and build for what comes next. If you're ready to explore
          new solutions, we would love to hear from you.
        </p>
        <a className="ad-btn ad-btn--primary" style={{ marginTop: 40 }}>
          <svg viewBox="0 0 16 16" fill="none"><path d="M3 8h10M9 4l4 4-4 4" stroke="white" strokeWidth="1.5"/></svg>
          GET STARTED
        </a>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer style={{ background: '#000', padding: '64px 120px', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
      <div>
        <img src="../../assets/logo.svg" style={{ height: 48 }} />
        <p style={{ fontSize: 17, marginTop: 24, maxWidth: 380, lineHeight: 1.5 }}>
          Agile Defense delivers advanced capabilities and solutions tailored
          to the most critical national security and civilian missions.
        </p>
      </div>
      <ul style={{ display: 'flex', gap: 32, listStyle: 'none', fontSize: 14, fontWeight: 500, letterSpacing: '.02em' }}>
        {['COMPANY','CAPABILITIES','NEWS','CAREERS','CONTACT'].map(l => <li key={l}>{l}</li>)}
      </ul>
      <div style={{ fontSize: 13, color: 'rgba(255,255,255,.5)' }}>
        Copyright 2026 · All rights reserved.
      </div>
    </footer>
  );
}

Object.assign(window, { AgileLabsSection, FinalCTA, Footer });
