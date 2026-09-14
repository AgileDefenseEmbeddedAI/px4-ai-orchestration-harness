/** Capability cards and purpose-driven section. */

function PurposeSection() {
  return (
    <section style={{ padding: '120px 120px 64px' }}>
      <div style={{ maxWidth: 920 }}>
        <h2 className="ad-h1">
          <span style={{ fontWeight: 700 }}>Purpose-Driven </span>
          <span style={{ fontWeight: 500 }}>Solutions</span>
        </h2>
        <p className="ad-body" style={{ maxWidth: 760, marginTop: 24 }}>
          At Agile Defense, we understand that outcomes are shaped by decisive
          actions, and emerging challenges demand innovative responses. Guided
          by a vision of the future, we navigate change with unwavering
          determination, forging pathways toward what lies ahead.
        </p>
        <p className="ad-body" style={{ maxWidth: 760, marginTop: 20 }}>
          Whether developing specialized solutions, contextualizing data, or
          strengthening cybersecurity, our expertise is instrumental in
          safeguarding our nation's sensitive assets.
        </p>
        <a className="ad-btn ad-btn--primary" style={{ marginTop: 40 }}>
          <svg viewBox="0 0 16 16" fill="none"><path d="M3 8h10M9 4l4 4-4 4" stroke="white" strokeWidth="1.5"/></svg>
          LEARN MORE
        </a>
      </div>
    </section>
  );
}

function CapabilityCards() {
  const cards = [
    { icon: '../../assets/icon-digital-transformation.svg', title: 'Digital Transformation',
      desc: 'Applying advanced services, capabilities, and solutions securely to enhance mission operations and achieve optimal outcomes.', featured: true },
    { icon: '../../assets/icon-data-analytics.svg', title: 'Data Analytics',
      desc: 'Leveraging a data-driven approach, we deliver data insights that provide clarity to accelerate the decision-making process.' },
    { icon: '../../assets/icon-cyber.svg', title: 'Cyber',
      desc: 'Delivering Cyber Systems and Cyber Operations capabilities to defend against advanced and emerging cyber threats with certainty.' },
  ];
  return (
    <section style={{ padding: '64px 120px 120px' }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 24 }}>
        {cards.map(c => (
          <div key={c.title}
               className={`ad-card ad-card--tall ${c.featured ? 'ad-card--featured' : ''}`}>
            <div className="ad-card__icon"><img src={c.icon} style={{width:'100%',height:'100%'}}/></div>
            <div style={{ marginTop: 'auto' }}>
              <div className="ad-card__title">{c.title}</div>
              <div className="ad-card__desc">{c.desc}</div>
              <a className="ad-btn ad-btn--secondary" style={{ marginTop: 32, color: '#fff' }}>
                LEARN MORE
                <svg viewBox="0 0 16 16" fill="none"><path d="M3 8h10M9 4l4 4-4 4" stroke="white" strokeWidth="1.5"/></svg>
              </a>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function CultureSection() {
  return (
    <section style={{ position: 'relative', height: 620, overflow: 'hidden' }}>
      <img src="../../assets/culture-image.jpg"
           style={{ position:'absolute', inset:0, width:'100%', height:'100%', objectFit:'cover' }} />
      <div style={{
        position:'absolute', inset:0,
        background:'linear-gradient(90deg, rgba(6,16,51,.9) 0%, rgba(6,16,51,.4) 60%, transparent 100%)',
      }} />
      <div style={{ position:'relative', padding:'120px', maxWidth: 900 }}>
        <h2 className="ad-h1" style={{ lineHeight: 1.05 }}>
          <span style={{ fontWeight: 700 }}>A Culture of </span>
          <span style={{ fontWeight: 500 }}>Innovation</span>
        </h2>
        <p className="ad-body" style={{ maxWidth: 520, marginTop: 24 }}>
          With a deep commitment to exploring new ideas and technologies, we
          invest in advancing the state of practice in every part of our
          organization.
        </p>
        <a className="ad-btn ad-btn--primary" style={{ marginTop: 40 }}>JOIN OUR TEAM</a>
      </div>
    </section>
  );
}

Object.assign(window, { PurposeSection, CapabilityCards, CultureSection });
