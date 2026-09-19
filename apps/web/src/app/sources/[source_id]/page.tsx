import { API_URL } from "@/lib/api";

type Props = {
  params: Promise<{ source_id: string }>;
};

type SourceDetail = {
  source_id: string;
  source_authority: string;
  source_type: string;
  source_url: string | null;
  document_title: string | null;
  content_sha256: string | null;
  verification_status: string;
  retrieved_at: string;
  collector_name: string | null;
  collector_version: string | null;
};

async function getSource(id: string): Promise<SourceDetail | null> {
  const res = await fetch(`${API_URL}/api/v1/sources/${id}`, { next: { revalidate: 60 } });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

export default async function SourcePage({ params }: Props) {
  const { source_id } = await params;
  let source: SourceDetail | null = null;
  try {
    source = await getSource(source_id);
  } catch {
    return (
      <div className="shell method-page">
        <p role="alert">Could not load source.</p>
      </div>
    );
  }
  if (!source) {
    return (
      <div className="shell method-page">
        <h1>Source not found</h1>
      </div>
    );
  }

  return (
    <div className="shell method-page">
      <h1>{source.source_id}</h1>
      <ul>
        <li>Authority: {source.source_authority}</li>
        <li>Type: {source.source_type}</li>
        <li>Status: {source.verification_status}</li>
        <li>Retrieved: {source.retrieved_at}</li>
        {source.document_title ? <li>Title: {source.document_title}</li> : null}
        {source.source_url ? (
          <li>
            URL:{" "}
            <a href={source.source_url} rel="noopener noreferrer">
              {source.source_url}
            </a>
          </li>
        ) : null}
        {source.content_sha256 ? <li>SHA-256: {source.content_sha256}</li> : null}
        {source.collector_name ? (
          <li>
            Collector: {source.collector_name} {source.collector_version}
          </li>
        ) : null}
      </ul>
    </div>
  );
}
