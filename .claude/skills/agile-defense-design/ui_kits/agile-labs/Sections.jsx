/** Stats + page header sections for the Agile Labs product page. */

function LabsHeader() {
  return (
    <>
      <nav className="ad-nav">
        <img className="ad-nav__logo" src="../../assets/logo.svg" alt="Agile Defense" />
        <ul className="ad-nav__links">
          <li className="ad-nav__item ad-nav__item--has-caret">Company</li>
          <li className="ad-nav__item ad-nav__item--has-caret">Capabilities</li>
          <li className="ad-nav__item ad-nav__item--has-caret" style={{ fontWeight: 700 }}>Agile Labs</li>
          <li className="ad-nav__item">Careers</li>
          <li className="ad-nav__item">News</li>
          <li><a className="ad-nav__cta">Contact</a></li>
        </ul>
      </nav>
      <section style={{ padding: '96px 120px 64px' }}>
        <div style={{ maxWidth: 920 }}>
          <div className="ad-eyebrow">Vertical-Specific Applications</div>
          <h1 className="ad-h1" style={{ fontSize: 96, fontWeight: 500, lineHeight: 1.05 }}>
            <span className="ad-red-dark" style={{ fontWeight: 700 }}>Mission </span>Impact
          </h1>
          <p className="ad-body" style={{ maxWidth: 640, marginTop: 32, fontSize: 20 }}>
            Mission-focused applications that deliver targeted solutions for
            government and defense challenges, powered by Agile Labs' underlying
            platform.
          </p>
          <div style={{ display: 'flex', gap: 24, marginTop: 40 }}>
            <a className="ad-btn ad-btn--primary">
              <svg viewBox="0 0 16 16" fill="none"><path d="M3 8h10M9 4l4 4-4 4" stroke="white" strokeWidth="1.5"/></svg>
              LEARN MORE
            </a>
            <a className="ad-btn ad-btn--secondary" style={{ color: '#fff' }}>
              <svg viewBox="0 0 16 16"><polygon points="6,3 13,8 6,13" fill="white"/></svg>
              SEE DEMO
            </a>
          </div>
        </div>
      </section>
    </>
  );
}

function StatsBanner() {
  return (
    <section style={{ padding: '32px 120px 64px' }}>
      <div style={{ display:'flex', alignItems:'center', gap: 64,
                    borderTop:'1px solid rgba(255,255,255,.08)',
                    borderBottom:'1px solid rgba(255,255,255,.08)',
                    padding:'48px 0' }}>
        <div>
          <div style={{ fontSize: 96, fontWeight: 700, color: '#d23c3a', lineHeight: 1 }}>91%</div>
          <div style={{ fontSize: 28, fontWeight: 400, marginTop: 8 }}>User Dissatisfaction</div>
        </div>
        <div style={{ fontSize: 22, fontWeight: 500, maxWidth: 720, lineHeight: 1.4 }}>
          If you're hearing your users call it "Nevermenlo," you're not alone —
          but the issue isn't Menlo itself; it's how it's integrated and operated.
        </div>
      </div>
    </section>
  );
}

function StatGrid() {
  const stats = [
    { v: '3.6M', l: 'Total Users Affected', c: 'blue' },
    { v: '847K', l: 'Daily Incidents', c: 'orange' },
    { v: '86%',  l: 'Avg. Severity Score', c: 'mid' },
    { v: '24%',  l: 'Productivity Loss', c: 'red' },
  ];
  return (
    <section style={{ padding: '0 120px 120px' }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 24 }}>
        {stats.map(s => (
          <div key={s.l} className={`ad-stat ad-stat--${s.c}`}>
            <div className="ad-stat__value">{s.v}</div>
            <div className="ad-stat__bar" />
            <div className="ad-stat__label">{s.l}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

function FixSection({ active, setActive }) {
  const problem = PROBLEMS.find(p => p.id === active);
  return (
    <section style={{ padding: '32px 120px 160px' }}>
      <div style={{ maxWidth: 1100, marginBottom: 48 }}>
        <h2 className="ad-h2" style={{ lineHeight: 1.15 }}>
          <span style={{ fontWeight: 700 }}>We Fix the Problems </span>
          <span style={{ fontWeight: 500 }}>Your Users Complain About</span>
        </h2>
        <p className="ad-h4" style={{ fontWeight: 500, marginTop: 16, opacity: .9 }}>
          Concrete failure modes mapped to mission-focused outcomes that deliver measurable results.
        </p>
      </div>
      <div style={{ display: 'flex', gap: 64, alignItems: 'flex-start' }}>
        <ProblemSidebar active={active} onSelect={setActive} />
        <ProblemDetail problem={problem} />
      </div>
    </section>
  );
}

Object.assign(window, { LabsHeader, StatsBanner, StatGrid, FixSection });
