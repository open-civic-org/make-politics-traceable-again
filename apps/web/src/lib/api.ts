export const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

const API_V1 = `${API_URL}/api/v1`;

export type PersonSummary = {
  person_id: string;
  canonical_name: string;
  current_party_name: string | null;
  current_office: string | null;
  constituency_name: string | null;
  state_name: string | null;
  is_demo: boolean;
};

export type PaginatedPeople = {
  items: PersonSummary[];
  page: number;
  page_size: number;
  total: number;
};

export type DeclaredValue = {
  value: string;
  declaration_year: number | null;
  source_id: string;
  verification_status: string;
  label: string;
};

export type ProvenanceRef = {
  source_id: string;
  source_authority: string | null;
  source_url: string | null;
  verification_status: string | null;
};

export type ElectionRecord = {
  election_id: string;
  year: number;
  election_type: string;
  constituency_name: string | null;
  party_name: string | null;
  candidate_name_as_published: string;
  votes_received: number | null;
  vote_share: string | null;
  result: string | null;
  rank: number | null;
  source: ProvenanceRef;
};

export type PersonDetail = PersonSummary & {
  aliases: string[];
  photo_url: string | null;
  education_declarations: DeclaredValue[];
  profession_declarations: DeclaredValue[];
  asset_declarations: DeclaredValue[];
  liability_declarations: DeclaredValue[];
  criminal_case_declarations: DeclaredValue[];
  income_declarations: DeclaredValue[];
  elections: ElectionRecord[];
  sources: ProvenanceRef[];
};

export async function searchPeople(q: string): Promise<PersonSummary[]> {
  const url = new URL(`${API_V1}/people`);
  if (q) url.searchParams.set("q", q);
  url.searchParams.set("page", "1");
  url.searchParams.set("page_size", "25");
  const res = await fetch(url.toString(), { next: { revalidate: 30 } });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  const data: PaginatedPeople = await res.json();
  return data.items;
}

export async function getPerson(personId: string): Promise<PersonDetail | null> {
  const res = await fetch(`${API_V1}/people/${personId}`, {
    next: { revalidate: 30 },
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}

export async function getSource(sourceId: string) {
  const res = await fetch(`${API_V1}/sources/${sourceId}`, {
    next: { revalidate: 60 },
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}
