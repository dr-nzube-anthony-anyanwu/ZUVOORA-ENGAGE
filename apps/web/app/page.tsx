export default function HomePage() {
  return (
    <main>
      <div className="brand">ZUBEVISION TECHNOLOGIES LTD.</div>
      <h1>ZUVOORA Engage</h1>
      <span className="status">Development workspace</span>
      <section className="panel">
        <h2>Welcome to the Engage control centre</h2>
        <p>This is the initial web application shell. Clinic onboarding, authentication, tenant administration, conversations and analytics will be delivered in later phases.</p>
        <p>Do not enter real clinic or patient information into this starter screen.</p>
      </section>
      <section className="panel">
        <h2>Build status</h2>
        <p>Phase 0 starter scaffold. API health endpoint: <code>http://localhost:8000/health/live</code></p>
      </section>
    </main>
  );
}
