import Link from "next/link";

export default function HomePage() {
  return (
    <main>
      <div className="brand">ZUBEVISION TECHNOLOGIES LTD.</div>
      <h1>ZUVOORA Engage</h1>
      <span className="status">Development workspace</span>
      <section className="panel">
        <h2>Clinic administration</h2>
        <p>Sign in to manage your clinic&apos;s Engage workspace. Access is by invitation only.</p>
        <p><Link href="/login" className="button">Sign in</Link></p>
        <p className="hint">Do not enter real patient information into this development environment.</p>
      </section>
    </main>
  );
}
