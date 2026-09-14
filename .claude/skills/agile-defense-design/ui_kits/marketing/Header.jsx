/** Marketing-site header and hero. Matches the Agile Defense homepage. */

function Navbar() {
  const items = [
    { label: 'Company', caret: true },
    { label: 'Capabilities', caret: true },
    { label: 'Agile Labs', caret: true },
    { label: 'Careers' },
    { label: 'News' },
    { label: 'Events' },
  ];
  return (
    <nav className="ad-nav">
      <img className="ad-nav__logo" src="../../assets/logo.svg" alt="Agile Defense" />
      <ul className="ad-nav__links">
        {items.map(it => (
          <li key={it.label}
              className={`ad-nav__item ${it.caret ? 'ad-nav__item--has-caret' : ''}`}>
            {it.label}
          </li>
        ))}
        <li><a className="ad-nav__cta">Contact</a></li>
      </ul>
    </nav>
  );
}

function Hero() {
  return (
    <section style={{
      position: 'relative', height: 760, overflow: 'hidden',
      display: 'flex', alignItems: 'flex-end',
    }}>
      <img src="../../assets/hero-image.jpg"
           style={{ position:'absolute', inset:0, width:'100%', height:'100%', objectFit:'cover' }} />
      <div style={{
        position:'absolute', inset:0,
        background: 'linear-gradient(180deg, rgba(6,16,51,.15) 0%, rgba(6,16,51,.85) 100%)',
      }} />
      <div style={{ position:'relative', padding: '0 120px 96px', width: '100%' }}>
        <h1 className="ad-hero-word">
          <span className="ad-red-dark" style={{ fontWeight: 700 }}>Always </span>
          <span style={{ fontWeight: 500 }}>Evolving</span>
        </h1>
        <p className="ad-body" style={{ maxWidth: 640, marginTop: 32, fontSize: 20 }}>
          Agile Defense stands at the forefront of innovation, driving advanced
          capabilities and solutions tailored to the most critical national
          security and civilian missions.
        </p>
      </div>
    </section>
  );
}

Object.assign(window, { Navbar, Hero });
