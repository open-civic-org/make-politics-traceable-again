import Link from "next/link";
import { searchPeople } from "@/lib/api";

type Props = {
  searchParams: Promise<{ q?: string }>;
};

export default async function HomePage({ searchParams }: Props) {
  const params = await searchParams;
  const q = params.q?.trim() ?? "";
  let results: Awaited<ReturnType<typeof searchPeople>> = [];
  let error: string | null = null;

  if (q) {
    try {
      results = await searchPeople(q);
    } catch {
      error = "Could not reach the API. Is it running on port 8000?";
    }
  }

  return (
    <div className="shell">
      <section className="hero">
        <h1>Make Politics Traceable Again</h1>
        <p className="lede">
          Search elected representatives and follow every claim to an official source.
          No scores. No rankings. No endorsements.
        </p>
        <form className="search-form" action="/" method="get" role="search">
          <label htmlFor="q" className="sr-only" style={{ position: "absolute", left: "-9999px" }}>
            Search politician
          </label>
          <input
            id="q"
            name="q"
            type="search"
            defaultValue={q}
            placeholder="Search by name"
            autoComplete="off"
          />
          <button type="submit">Search</button>
        </form>
      </section>

      {error ? <p role="alert">{error}</p> : null}

      {q ? (
        <section className="results" aria-live="polite">
          <h2 style={{ fontFamily: "var(--font-display)", fontSize: "1.25rem" }}>
            Results for “{q}”
          </h2>
          {results.length === 0 ? (
            <p>No matching people in the database.</p>
          ) : (
            <ul>
              {results.map((p) => (
                <li key={p.person_id}>
                  <Link href={`/person/${p.person_id}`}>
                    <strong>{p.canonical_name}</strong>
                    <div className="meta">
                      {[p.current_office, p.constituency_name, p.state_name, p.current_party_name]
                        .filter(Boolean)
                        .join(" · ")}
                      {p.is_demo ? " · Demo data" : ""}
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : null}
    </div>
  );
}
