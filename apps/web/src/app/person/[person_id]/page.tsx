import Link from "next/link";
import { notFound } from "next/navigation";
import { getPerson } from "@/lib/api";

type Props = {
  params: Promise<{ person_id: string }>;
};

function DeclaredList({
  items,
}: {
  items: {
    value: string;
    declaration_year: number | null;
    source_id: string;
    verification_status: string;
    label: string;
  }[];
}) {
  if (!items.length) return <p>No declarations on record.</p>;
  return (
    <ul>
      {items.map((item, i) => (
        <li key={`${item.source_id}-${i}`}>
          {item.value}
          <div className="declared">
            {item.label}
            {item.declaration_year ? ` (${item.declaration_year})` : ""} ·{" "}
            {item.verification_status} ·{" "}
            <Link href={`/sources/${item.source_id}`}>{item.source_id}</Link>
          </div>
        </li>
      ))}
    </ul>
  );
}

export default async function PersonPage({ params }: Props) {
  const { person_id } = await params;
  let person;
  try {
    person = await getPerson(person_id);
  } catch {
    return (
      <div className="shell person-page">
        <p role="alert">Could not load this person. Is the API running?</p>
      </div>
    );
  }
  if (!person) notFound();

  return (
    <div className="shell person-page">
      {person.is_demo ? (
        <div className="demo-banner" role="status">
          Demo data — fictional representative for development. Not a real politician.
        </div>
      ) : null}

      <h1>{person.canonical_name}</h1>
      <p className="subtitle">
        {[person.current_office, person.constituency_name, person.state_name, person.current_party_name]
          .filter(Boolean)
          .join(" · ")}
      </p>
      {person.aliases.length > 0 ? (
        <p className="declared">Also known as: {person.aliases.join(", ")}</p>
      ) : null}

      <section className="section">
        <h2>Background (self-declared)</h2>
        <h3 style={{ fontSize: "1rem", marginBottom: "0.35rem" }}>Education</h3>
        <DeclaredList items={person.education_declarations} />
        <h3 style={{ fontSize: "1rem", margin: "1rem 0 0.35rem" }}>Profession</h3>
        <DeclaredList items={person.profession_declarations} />
      </section>

      <section className="section">
        <h2>Elections</h2>
        {person.elections.length === 0 ? (
          <p>No election records.</p>
        ) : (
          <ul>
            {person.elections.map((e) => (
              <li key={e.election_id}>
                {e.year} {e.election_type.replaceAll("_", " ")}
                {e.constituency_name ? ` — ${e.constituency_name}` : ""}
                {e.result ? ` · ${e.result}` : ""}
                {e.votes_received != null ? ` · ${e.votes_received.toLocaleString()} votes` : ""}
                {e.vote_share != null ? ` (${e.vote_share}%)` : ""}
                <div className="declared">
                  Source: <Link href={`/sources/${e.source.source_id}`}>{e.source.source_id}</Link>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="section">
        <h2>Affidavit declarations</h2>
        <h3 style={{ fontSize: "1rem", marginBottom: "0.35rem" }}>Assets</h3>
        <DeclaredList items={person.asset_declarations} />
        <h3 style={{ fontSize: "1rem", margin: "1rem 0 0.35rem" }}>Liabilities</h3>
        <DeclaredList items={person.liability_declarations} />
        <h3 style={{ fontSize: "1rem", margin: "1rem 0 0.35rem" }}>Income</h3>
        <DeclaredList items={person.income_declarations} />
        <h3 style={{ fontSize: "1rem", margin: "1rem 0 0.35rem" }}>
          Cases declared in election affidavit
        </h3>
        <DeclaredList items={person.criminal_case_declarations} />
      </section>

      <section className="section">
        <h2>Sources</h2>
        <ul>
          {person.sources.map((s) => (
            <li key={s.source_id}>
              <Link href={`/sources/${s.source_id}`}>{s.source_id}</Link>
              {s.source_authority ? ` — ${s.source_authority}` : ""}
              {s.verification_status ? ` (${s.verification_status})` : ""}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
