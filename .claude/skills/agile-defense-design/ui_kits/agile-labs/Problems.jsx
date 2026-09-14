/** Agile Labs product page — Mission Impact layout.
 *  Sidebar + detail panel for each problem area. */

const PROBLEMS = [
  {
    id: 'login',
    title: 'Login, CAC, and Identity Friction',
    icon: (<svg viewBox="0 0 24 24"><rect x="5" y="9" width="14" height="11" rx="1"/><path d="M8 9V6a4 4 0 018 0v3"/></svg>),
    challenge: 'Endless re-authentication prompts and certificate loops strand users between systems and break workflow continuity.',
    approach: 'Profile auth failure patterns across top-10 mission apps. Tune CAC middleware, session timeouts, and SSO token exchange so the identity layer stops leaking into the user\'s day.',
    result: 'Fewer than 2 auth prompts per user per shift.',
    metric: '94% reduction in identity friction tickets',
  },
  {
    id: 'pages',
    title: 'Pages That Constantly Refresh, Hang, or Break',
    icon: (<svg viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16"/><path d="M8 8l8 8M16 8l-8 8"/></svg>),
    challenge: 'Critical sites time out, blank-screen, or enter infinite refresh loops — especially government portals and training sites.',
    approach: 'Profile problematic sites and identify rendering/script conflicts. Adjust Menlo isolation modes and browser compatibility settings. Certify high-value apps through controlled tuning and regression testing.',
    result: 'Mission-critical sites load reliably the first time.',
    metric: '99.5% uptime on certified sites',
  },
  {
    id: 'downloads',
    title: 'Download & File-Handling Friction',
    icon: (<svg viewBox="0 0 24 24"><path d="M12 4v12M6 12l6 6 6-6M4 20h16"/></svg>),
    challenge: 'Downloads fail or return files stripped of critical content, forcing analysts to chase raw source material through side channels.',
    approach: 'Instrument the file-handling path end-to-end. Whitelist mission file types, correct MIME negotiation, and eliminate CDR strips that break the document.',
    result: 'Analysts get the file they asked for, intact, on the first try.',
    metric: '100% fidelity on approved file types',
  },
  {
    id: 'media',
    title: 'Broken Media, SaaS, and Collaboration Tools',
    icon: (<svg viewBox="0 0 24 24"><polygon points="8,5 19,12 8,19" fill="currentColor" stroke="none"/></svg>),
    challenge: 'Video calls drop. Shared documents freeze. Standard SaaS that works everywhere else just doesn\'t work here.',
    approach: 'Targeted tuning per app. Lock browser versions where needed, stage rollouts behind telemetry, and keep a rollback lane ready.',
    result: 'Teams stop working around the tools and start working with them.',
    metric: '3x fewer media-related support calls',
  },
  {
    id: 'browser',
    title: 'Browser Compatibility & Endpoint Drift',
    icon: (<svg viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18"/><line x1="9" y1="3" x2="9" y2="21"/></svg>),
    challenge: 'A fleet of subtly-different browser builds across endpoints creates a debugging tax that scales with the org.',
    approach: 'Establish a supported-browser matrix. Automate drift detection. Roll fixes forward, not sideways.',
    result: 'One known-good config across the fleet.',
    metric: '< 48h mean time to patch fleet drift',
  },
  {
    id: 'latency',
    title: 'Latency, Lag, and "NIPR Is a Hassle"',
    icon: (<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3" fill="currentColor" stroke="none"/></svg>),
    challenge: 'Users describe the network as the problem. Often it isn\'t — but the app stack makes it feel that way.',
    approach: 'Trace real user journeys. Eliminate redundant round-trips, pre-warm isolation workers, and move heavy assets closer to the user.',
    result: 'Perceived latency drops into the "I don\'t think about it" range.',
    metric: '62% faster median page load',
  },
];

function ProblemSidebar({ active, onSelect }) {
  return (
    <div className="ad-side">
      {PROBLEMS.map(p => (
        <div key={p.id}
             className={`ad-side__item ${active === p.id ? 'ad-side__item--active' : ''}`}
             onClick={() => onSelect(p.id)}>
          <div className="ad-side__icon">{p.icon}</div>
          <div className="ad-side__text">{p.title}</div>
        </div>
      ))}
    </div>
  );
}

function ProblemDetail({ problem }) {
  return (
    <div className="ad-detail">
      <div className="ad-detail__section">
        <div className="ad-detail__icon">
          <svg viewBox="0 0 48 48"><rect x="8" y="8" width="32" height="32"/><path d="M16 16l16 16M32 16L16 32"/></svg>
        </div>
        <div>
          <div className="ad-detail__title">Challenge</div>
          <div className="ad-detail__body">{problem.challenge}</div>
        </div>
      </div>
      <div className="ad-detail__section">
        <div className="ad-detail__icon">
          <svg viewBox="0 0 48 48"><circle cx="24" cy="24" r="16"/><path d="M24 8v32M8 24h32"/></svg>
        </div>
        <div>
          <div className="ad-detail__title">Our Approach</div>
          <div className="ad-detail__body">{problem.approach}</div>
        </div>
      </div>
      <div className="ad-detail__section">
        <div className="ad-detail__icon">
          <svg viewBox="0 0 48 48"><rect x="6" y="6" width="36" height="36"/><path d="M14 24l6 6 14-14" strokeWidth="3"/></svg>
        </div>
        <div>
          <div className="ad-detail__title">Result</div>
          <div className="ad-detail__body">{problem.result}</div>
          <div className="ad-detail__body" style={{ color: '#ff5a58' }}>{problem.metric}</div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { PROBLEMS, ProblemSidebar, ProblemDetail });
