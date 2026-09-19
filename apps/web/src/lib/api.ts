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

export type EducationDeclaration = {
  declared_value: string;
  normalized_level: string | null;
  institution_raw: string | null;
  year_raw: string | null;
  declaration_year: number | null;
  verification_status: string;
  source_id: string;
  label: string;
};

export type FinancialDeclaration = {
  category: string | null;
  description: string;
  amount_raw: string | null;
  amount: string | null;
  currency: string | null;
  declaration_year: number | null;
  verification_status: string;
  source_id: string;
  label: string;
};

export type CaseDeclaration = {
  case_summary: string;
  case_number_raw: string | null;
  court_raw: string | null;
  act_raw: string | null;
  section_raw: string | null;
  status_raw: string | null;
  normalized_status: string | null;
  declaration_year: number | null;
  verification_status: string;
  source_id: string;
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
  education_declarations: EducationDeclaration[];
  profession_declarations: DeclaredValue[];
  asset_declarations: FinancialDeclaration[];
  liability_declarations: FinancialDeclaration[];
  criminal_case_declarations: CaseDeclaration[];
  income_declarations: FinancialDeclaration[];
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
