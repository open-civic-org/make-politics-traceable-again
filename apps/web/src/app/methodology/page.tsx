export default function MethodologyPage() {
  return (
    <div className="shell method-page">
      <h1>Methodology</h1>
      <p>
        This project publishes evidence-based records about elected representatives. Every
        material claim is meant to link back to an official source document.
      </p>
      <h2>Neutrality</h2>
      <p>
        We do not score, rank, endorse, or recommend politicians or parties. Measurable
        records (election results, declared assets, questions asked) may appear; interpretation
        is left to the reader.
      </p>
      <h2>Declarations</h2>
      <p>
        Education, profession, assets, liabilities, income, and cases taken from election
        affidavits are shown as self-declared, not as independently verified facts, unless a
        separate verification exists.
      </p>
      <h2>Provenance</h2>
      <p>
        Claims should resolve to: person → office at that time → action or declaration → date →
        jurisdiction → source authority → original document (URL, hash, retrieval metadata).
      </p>
    </div>
  );
}
