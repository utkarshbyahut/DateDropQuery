import { kv } from "@vercel/kv";

export const revalidate = 30;

export default async function Home() {
  const data = await kv.get("asu:latest");

  if (!data) {
    return (
      <main style={{ padding: 24, fontFamily: "system-ui" }}>
        <h1>ASU Waitlist</h1>
        <p>No data yet. The cron will populate this soon.</p>
      </main>
    );
  }

  return (
    <main style={{ padding: 24, fontFamily: "system-ui", maxWidth: 720 }}>
      <h1>ASU Waitlist</h1>

      <div style={{ marginTop: 16, padding: 16, border: "1px solid #ddd", borderRadius: 12 }}>
        <div style={{ fontSize: 18, marginBottom: 8 }}>
          Current rank: <strong>#{data.schoolRank ?? "unknown"}</strong>
        </div>
        <div>Signup count: <strong>{data.schoolSignupCount ?? "unknown"}</strong></div>
        <div style={{ marginTop: 12, opacity: 0.75 }}>
          Updated: {data.timestampUtc}
        </div>
      </div>
    </main>
  );
}
