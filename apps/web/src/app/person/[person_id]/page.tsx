import Link from "next/link";
import { notFound } from "next/navigation";
import {
  type CaseDeclaration,
  type DeclaredValue,
  type EducationDeclaration,
  type FinancialDeclaration,
  getPerson,
} from "@/lib/api";

type Props = {
  params: Promise<{ person_id: string }>;
};

function SourceLine({
  label,
  year,
  status,
  sourceId,
}: {
  label: string;
  year: number | null;
  status: string;
  sourceId: string;
}) {
  return (
    <div className="declared">
      {label}
      {year ? ` (${year})` : ""} · {status} ·{" "}
      <Link href={`/sources/${sourceId}`}>{sourceId}</Link>
    </div>
  );
}

function DeclaredList({ items }: { items: DeclaredValue[] }) {
  if (!items.length) return <p>No declarations on record.</p>;
  return (
    <ul>
      {items.map((item, i) => (
        <li key={`${item.source_id}-${i}`}>
          {item.value}
          <SourceLine
            label={item.label}
            year={item.declaration_year}
            status={item.verification_status}
            sourceId={item.source_id}
          />
        </li>
      ))}
    </ul>
  );
}

function EducationList({ items }: { items: EducationDeclaration[] }) {
  if (!items.length) return <p>No declarations on record.</p>;
  return (
    <ul>
      {items.map((item, i) => (
        <li key={`${item.source_id}-${i}`}>
          {item.declared_value}
          {item.normalized_level ? ` · ${item.normalized_level}` : ""}
          {item.institution_raw ? ` · ${item.institution_raw}` : ""}
          <SourceLine
            label={item.label}
            year={item.declaration_year}
            status={item.verification_status}
            sourceId={item.source_id}
          />
        </li>
      ))}
    </ul>
  );
}

function FinancialList({ items }: { items: FinancialDeclaration[] }) {
  if (!items.length) return <p>No declarations on record.</p>;
  return (
    <ul>
      {items.map((item, i) => (
        <li key={`${item.source_id}-${i}`}>
          {item.category ? `${item.category}: ` : ""}
          {item.description}
          {item.amount_raw
            ? ` — ${item.amount_raw}`
            : item.amount
              ? ` — ${item.currency || "INR"} ${item.amount}`
              : ""}
          <SourceLine
            label={item.label}
            year={item.declaration_year}
            status={item.verification_status}
            sourceId={item.source_id}
          />
        </li>
      ))}
    </ul>
  );
}

function CaseList({ items }: { items: CaseDeclaration[] }) {
  if (!items.length) return <p>No declarations on record.</p>;
  return (
    <ul>
      {items.map((item, i) => (
        <li key={`${item.source_id}-${i}`}>
          {item.normalized_status ? `[${item.normalized_status}] ` : ""}
          {item.case_summary}
          {item.case_number_raw ? ` · ${item.case_number_raw}` : ""}
          <SourceLine
            label={item.label}
            year={item.declaration_year}
            status={item.verification_status}
            sourceId={item.source_id}
          />
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
        <h2>Declared education</h2>
        <EducationList items={person.education_declarations} />
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
        <h2>Declared assets</h2>
        <FinancialList items={person.asset_declarations} />
        <h2 style={{ marginTop: "1.25rem" }}>Declared liabilities</h2>
        <FinancialList items={person.liability_declarations} />
        <h3 style={{ fontSize: "1rem", margin: "1rem 0 0.35rem" }}>Declared income</h3>
        <FinancialList items={person.income_declarations} />
        <h2 style={{ marginTop: "1.25rem" }}>Declared cases</h2>
        <p className="declared" style={{ marginBottom: "0.5rem" }}>
          Criminal-case disclosures as self-declared in the election affidavit — not a finding of guilt.
        </p>
        <CaseList items={person.criminal_case_declarations} />
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
